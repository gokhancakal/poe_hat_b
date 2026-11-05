import smbus
import psutil
import socket
import logging
import time
import math
from PIL import Image, ImageDraw, ImageFont
import SSD1306

class PoeHatB:
    def __init__(self, address=0x20):
        self.i2c = smbus.SMBus(1)
        self.address = address
        self.fan_mode = None
        self.show = None
        self.display_retry_at = 0
        self.errors = set()
        self.font = getattr(ImageFont, "load_default_imagefont", ImageFont.load_default)()
        self._ip_cache = None
        self._ip_cache_at = 0
        self.page_index = 0
        self.last_page_switch = time.monotonic()
        try:
            self.fan_on()
        except OSError:
            self.i2c.close()
            raise
        psutil.cpu_percent(None)
        self.cpu_ready = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def fan_on(self):
        if self.fan_mode != 1:
            self.i2c.write_byte(self.address, 0xFE & self.i2c.read_byte(self.address))
            self.fan_mode = 1
            logging.info("Fan ON")

    def fan_off(self):
        if self.fan_mode != 0:
            self.i2c.write_byte(self.address, 0x01 | self.i2c.read_byte(self.address))
            self.fan_mode = 0
            logging.info("Fan OFF")

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
        try:
            if temp is None or temp >= fan_temp:
                self.fan_on()
            elif temp < fan_off_temp:
                self.fan_off()
            elif self.fan_mode is None:
                self.fan_on()
            self.report_error("fan")
        except OSError as error:
            self.fan_mode = None
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
        bbox = self.font.getbbox(text)
        return bbox[2] - bbox[0]

    @staticmethod
    def draw_progress_bar(draw, x, y, width, height, percent):
        pct = max(0.0, min(100.0, float(percent)))
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=0)
        inner_width = max(0, width - 4)
        inner_height = max(0, height - 4)
        fill_width = int(round((pct / 100.0) * inner_width))
        if fill_width > 0:
            draw.rectangle(
                (x + 2, y + 2, x + 2 + fill_width - 1, y + 2 + inner_height - 1),
                fill=0
            )

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

        draw.text((4, 2), "IP:", font=self.font, fill=0)
        draw.text((36, 2), str(ip), font=self.font, fill=0)

        draw.text((4, 12), "HOST:", font=self.font, fill=0)
        draw.text((36, 12), str(hostname), font=self.font, fill=0)

        draw.text((4, 22), "UP:", font=self.font, fill=0)
        draw.text((36, 22), str(uptime_str), font=self.font, fill=0)
        draw.text((109, 22), "1/3", font=self.font, fill=0)

    def render_page_2(self, draw):
        """Sayfa 2: CPU ve RAM Barları."""
        try:
            memory = self.get_memory()
            cpu = self.get_cpu()
            self.report_error("metrics")
        except (OSError, ValueError, psutil.Error) as error:
            memory = cpu = None
            self.report_error("metrics", error)

        cpu_val = 0.0 if cpu is None else cpu
        ram_val = 0.0 if memory is None else memory
        s_cpu = f"CPU {cpu_val:.0f}%" if cpu is not None else "CPU --%"
        s_ram = f"RAM {ram_val:.0f}%" if memory is not None else "RAM --%"

        w_cpu = self._get_text_width(s_cpu)
        w_ram = self._get_text_width(s_ram)

        draw.text((4 + (56 - w_cpu) // 2, 2), s_cpu, font=self.font, fill=0)
        draw.text((68 + (56 - w_ram) // 2, 2), s_ram, font=self.font, fill=0)

        self.draw_progress_bar(draw, 4, 12, 56, 7, cpu_val)
        self.draw_progress_bar(draw, 68, 12, 56, 7, ram_val)

        status = "LOAD HIGH" if (cpu_val > 80 or ram_val > 85) else "LOAD NORMAL"
        draw.text((4, 22), status, font=self.font, fill=0)
        draw.text((109, 22), "2/3", font=self.font, fill=0)

    def render_page_3(self, draw, temp, fan_temp, fan_off_temp):
        """Sayfa 3: Sıcaklık ve Fan (Termal Bar)."""
        temp_val = 30.0 if temp is None else temp
        s_temp = f"TEMP: {temp_val:.1f}C" if temp is not None else "TEMP: --.-C"
        s_fan = "[FAN ON]" if self.fan_mode == 1 else "[FAN OFF]" if self.fan_mode == 0 else "[FAN --]"
        w_fan = self._get_text_width(s_fan)

        draw.text((4, 2), s_temp, font=self.font, fill=0)
        draw.text((124 - w_fan, 2), s_fan, font=self.font, fill=0)

        min_t, max_t = 30.0, 75.0
        pct = max(0.0, min(100.0, ((temp_val - min_t) / (max_t - min_t)) * 100.0))
        self.draw_progress_bar(draw, 4, 12, 120, 7, pct)

        thresh_pct = (fan_temp - min_t) / (max_t - min_t)
        tick_x = int(round(4 + 2 + thresh_pct * (120 - 4)))
        draw.line([(tick_x, 10), (tick_x, 20)], fill=0, width=1)

        draw.text((4, 22), f"ON>={fan_temp:.0f}C OFF<{fan_off_temp:.0f}C", font=self.font, fill=0)
        draw.text((109, 22), "3/3", font=self.font, fill=0)

    def poe_hat_display(self, fan_temp, fan_off_temp=None, page_interval=3.0):
        if fan_off_temp is None:
            fan_off_temp = fan_temp - 2
        temp = self.update_fan(fan_temp, fan_off_temp)
        if time.monotonic() < self.display_retry_at:
            return

        now = time.monotonic()
        if now - self.last_page_switch >= page_interval:
            self.page_index = (self.page_index + 1) % 3
            self.last_page_switch = now

        try:
            if self.show is None:
                self.show = SSD1306.SSD1306()
                self.show.Init()
            image = Image.new('1', (self.show.width, self.show.height), "WHITE")
            draw = ImageDraw.Draw(image)

            if self.page_index == 0:
                self.render_page_1(draw)
            elif self.page_index == 1:
                self.render_page_2(draw)
            else:
                self.render_page_3(draw, temp, fan_temp, fan_off_temp)

            self.show.ShowImage(self.show.getbuffer(image))
            self.report_error("display")
        except (OSError, ValueError) as error:
            self.report_error("display", error)
            self.close_display()
            self.display_retry_at = time.monotonic() + 30

    def close_display(self):
        if self.show is not None:
            try:
                self.show.Closebus()
            except OSError:
                pass
            self.show = None

    def close(self):
        try:
            self.fan_on()
        except OSError as error:
            self.fan_mode = None
            self.report_error("fan", error)
        finally:
            self.close_display()
            self.i2c.close()
