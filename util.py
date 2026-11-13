import math
import logging
import socket
import time
import psutil
import smbus
from PIL import Image, ImageDraw, ImageFont, ImageChops

import drivers
from controllers import get_fan_controller, PoeFanController, DummyFanController
from renderers import draw_progress_bar, get_text_width, View128x32, View128x64


class PoeHatB:
    draw_progress_bar = staticmethod(draw_progress_bar)

    def __init__(self, address=0x20, display_type="poe", fan_type="poe",
                 contrast=50, pixel_shift=True, screen_timeout=0.0):
        self.display_type = str(display_type).strip().lower()
        self.fan_type = str(fan_type).strip().lower()
        self.address = address
        self.contrast = max(1, min(255, int(contrast)))
        self.pixel_shift = bool(pixel_shift)
        self.screen_timeout = max(0.0, float(screen_timeout))
        self.screen_on = True
        self.last_active_time = time.monotonic()
        self.manual_wake_until = 0.0
        self.last_temp = None
        self.shift_index = 4

        self.fan_controller = get_fan_controller(self.fan_type, address=self.address)
        self.fan_enabled = self.fan_controller.enabled

        self.show = None
        self.display_retry_at = 0
        self.errors = set()
        self.font = getattr(ImageFont, "load_default_imagefont", ImageFont.load_default)()
        self._ip_cache = None
        self._ip_cache_at = 0
        self.page_index = 0
        self.last_page_switch = time.monotonic()

        self.renderer_32 = View128x32(self.font)
        self.renderer_64 = View128x64(self.font)

        psutil.cpu_percent(None)
        self.cpu_ready = False

    def wake_display(self):
        """Wake up display from sleep mode."""
        if not self.screen_on:
            if self.show is not None:
                self.show.wake()
            self.screen_on = True
            self.last_active_time = time.monotonic()

    def sleep_display(self):
        """Put display to low-power blank sleep mode."""
        if self.screen_on:
            if self.show is not None:
                self.show.sleep()
            self.screen_on = False

    def request_wake(self, duration=60):
        self.manual_wake_until = max(
            self.manual_wake_until, time.monotonic() + max(0.0, duration)
        )

    @property
    def i2c(self):
        return getattr(self.fan_controller, "i2c", None)

    @i2c.setter
    def i2c(self, value):
        if hasattr(self.fan_controller, "i2c"):
            self.fan_controller.i2c = value

    @property
    def fan_mode(self):
        return self.fan_controller.fan_mode

    @fan_mode.setter
    def fan_mode(self, value):
        self.fan_controller.fan_mode = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def fan_on(self):
        if not self.fan_enabled:
            return
        self.fan_controller.fan_on()

    def fan_off(self):
        if not self.fan_enabled:
            return
        self.fan_controller.fan_off()

    def get_ip(self):
        now = time.monotonic()
        if self._ip_cache is None or now - self._ip_cache_at > 30:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('8.8.8.8', 80))
                self._ip_cache = s.getsockname()[0]
                self._ip_cache_at = now
        return self._ip_cache

    def get_memory(self):
        return psutil.virtual_memory().percent

    def get_cpu(self):
        cpu = psutil.cpu_percent(None)
        if not self.cpu_ready:
            self.cpu_ready = True
            return None
        return cpu

    def get_temp(self):
        with open('/sys/class/thermal/thermal_zone0/temp', 'rt') as f:
            temp = int(f.read().strip()) / 1000.0
        return temp

    def report_error(self, name, error=None):
        if error is not None:
            if name not in self.errors:
                logging.warning("%s: %s", name, error)
                self.errors.add(name)
        elif name in self.errors:
            logging.info("%s recovered", name)
            self.errors.remove(name)

    def update_fan(self, fan_temp, fan_off_temp):
        try:
            temp = self.get_temp()
            if not math.isfinite(temp):
                raise ValueError("Invalid temperature")
            self.report_error("temperature")
        except (OSError, ValueError) as error:
            self.report_error("temperature", error)
            temp = None

        if self.fan_enabled:
            try:
                self.fan_controller.update(temp, fan_temp, fan_off_temp)
                self.report_error("fan")
            except OSError as error:
                self.fan_controller.fan_mode = None
                self.report_error("fan", error)
        return temp

    def get_hostname(self):
        try:
            return socket.gethostname()
        except OSError:
            return "--"

    def get_uptime(self):
        try:
            with open('/proc/uptime', 'rt') as f:
                uptime_seconds = float(f.readline().split()[0])
        except (OSError, ValueError):
            try:
                uptime_seconds = time.time() - psutil.boot_time()
            except Exception:
                return "--"
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def _get_text_width(self, text):
        return get_text_width(self.font, text)

    def render_page_1(self, draw):
        """Sayfa 1: IP, Hostname ve Uptime."""
        try:
            ip = self.get_ip()
            self.report_error("network")
        except OSError as error:
            self._ip_cache = None
            ip = "--"
            self.report_error("network", error)

        hostname = self.get_hostname()
        uptime_str = self.get_uptime()
        self.renderer_32.render_page_1(draw, ip, hostname, uptime_str)

    def render_page_2(self, draw):
        """Sayfa 2: CPU ve RAM Barları."""
        try:
            memory = self.get_memory()
            cpu = self.get_cpu()
            self.report_error("metrics")
        except (OSError, ValueError, psutil.Error) as error:
            memory = cpu = None
            self.report_error("metrics", error)

        self.renderer_32.render_page_2(draw, cpu, memory)

    def render_page_3(self, draw, temp, fan_temp, fan_off_temp):
        """Sayfa 3: Sıcaklık ve Fan (Termal Bar - 128x32)."""
        self.renderer_32.render_page_3(
            draw, temp, self.fan_mode, fan_temp, fan_off_temp, fan_enabled=self.fan_enabled
        )

    def render_page_1_64(self, draw):
        """Sayfa 1 (128x64): Ağ & Sistem Bilgisi."""
        try:
            ip = self.get_ip()
            self.report_error("network")
        except OSError as error:
            self._ip_cache = None
            ip = "--"
            self.report_error("network", error)

        hostname = self.get_hostname()
        uptime_str = self.get_uptime()
        self.renderer_64.render_page_1(draw, ip, hostname, uptime_str)

    def render_page_2_64(self, draw):
        """Sayfa 2 (128x64): İşlemci & Bellek Barları."""
        try:
            memory = self.get_memory()
            cpu = self.get_cpu()
            self.report_error("metrics")
        except (OSError, ValueError, psutil.Error) as error:
            memory = cpu = None
            self.report_error("metrics", error)

        self.renderer_64.render_page_2(draw, cpu, memory)

    def render_page_3_64(self, draw, temp, fan_temp, fan_off_temp):
        """Sayfa 3 (128x64): Sıcaklık ve Fan (Termal Bar)."""
        self.renderer_64.render_page_3(
            draw, temp, self.fan_mode, fan_temp, fan_off_temp, fan_enabled=self.fan_enabled
        )

    def poe_hat_display(self, fan_temp, fan_off_temp=None, page_interval=3.0):
        if fan_off_temp is None:
            fan_off_temp = fan_temp - 2
        previous_fan_mode = self.fan_mode
        temp = self.update_fan(fan_temp, fan_off_temp)
        if time.monotonic() < self.display_retry_at:
            return

        now = time.monotonic()
        fan_started = self.fan_mode == 1 and previous_fan_mode != 1
        temp_reached_threshold = (
            temp is not None and temp >= fan_temp
            and (self.last_temp is None or self.last_temp < fan_temp)
        )
        self.last_temp = temp
        manual_wake_active = 0 < self.manual_wake_until and now < self.manual_wake_until
        manual_wake_expired = 0 < self.manual_wake_until <= now
        try:
            if manual_wake_active:
                self.wake_display()
            elif fan_started or temp_reached_threshold:
                self.last_active_time = now
                self.wake_display()
            elif self.screen_timeout > 0 and (
                manual_wake_expired
                or now - self.last_active_time >= self.screen_timeout
            ):
                self.sleep_display()
                self.manual_wake_until = 0.0
                return
            if manual_wake_expired:
                self.manual_wake_until = 0.0
        except (OSError, ValueError, RuntimeError) as error:
            self.report_error("display", error)
            self.close_display()
            self.display_retry_at = time.monotonic() + 30
            return

        if now - self.last_page_switch >= page_interval:
            self.page_index = (self.page_index + 1) % 3
            self.last_page_switch = now
            self.shift_index = (self.shift_index + 1) % 9

        try:
            if self.show is None:
                if self.display_type == "waveshare-1.3":
                    self.show = drivers.SH1106()
                else:
                    self.show = drivers.SSD1306()
                self.show.Init(self.contrast)
                self.screen_on = True
            image = Image.new('1', (self.show.width, self.show.height), "WHITE")
            draw = ImageDraw.Draw(image)

            if getattr(self.show, "height", 32) == 64:
                if self.page_index == 0:
                    self.render_page_1_64(draw)
                elif self.page_index == 1:
                    self.render_page_2_64(draw)
                else:
                    self.render_page_3_64(draw, temp, fan_temp, fan_off_temp)
            else:
                if self.page_index == 0:
                    self.render_page_1(draw)
                elif self.page_index == 1:
                    self.render_page_2(draw)
                else:
                    self.render_page_3(draw, temp, fan_temp, fan_off_temp)

            if self.pixel_shift:
                dx = self.shift_index % 3 - 1
                dy = self.shift_index // 3 - 1
                image = ImageChops.offset(image, dx, dy)
                shifted_draw = ImageDraw.Draw(image)
                if dx > 0:
                    shifted_draw.rectangle((0, 0, 0, image.height - 1), fill=1)
                elif dx < 0:
                    shifted_draw.rectangle(
                        (image.width - 1, 0, image.width - 1, image.height - 1), fill=1
                    )
                if dy > 0:
                    shifted_draw.rectangle((0, 0, image.width - 1, 0), fill=1)
                elif dy < 0:
                    shifted_draw.rectangle(
                        (0, image.height - 1, image.width - 1, image.height - 1), fill=1
                    )
            self.show.ShowImage(self.show.getbuffer(image))
            self.report_error("display")
        except (OSError, ValueError, RuntimeError) as error:
            self.report_error("display", error)
            self.close_display()
            self.display_retry_at = time.monotonic() + 30

    def close_display(self):
        if self.show is not None:
            try:
                self.show.Closebus()
            except Exception:
                pass
            self.show = None

    def close(self):
        try:
            if self.fan_enabled:
                self.fan_controller.close()
        except OSError as error:
            self.report_error("fan", error)
        finally:
            self.close_display()
