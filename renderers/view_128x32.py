"""Renderer for 128x32 OLED display (SSD1306 / PoE HAT B default)."""
from .common import draw_progress_bar, get_text_width, fit_text, load_status


class View128x32:
    """Renders 3-page status views optimized for 128x32 OLED."""
    def __init__(self, font):
        self.font = font

    def render_page_1(self, draw, ip, hostname, uptime_str):
        """Page 1: IP, Hostname, and Uptime."""
        draw.text((4, 1), "IP:", font=self.font, fill=0)
        draw.text((34, 1), fit_text(self.font, ip, 90), font=self.font, fill=0)

        draw.text((4, 11), "HOST:", font=self.font, fill=0)
        draw.text((34, 11), fit_text(self.font, hostname, 90), font=self.font, fill=0)

        draw.text((4, 20), "UP:", font=self.font, fill=0)
        draw.text((34, 20), fit_text(self.font, uptime_str, 66), font=self.font, fill=0)
        draw.text((109, 20), "1/3", font=self.font, fill=0)

    def render_page_2(self, draw, cpu, memory):
        """Page 2: Dual CPU and RAM progress bars with status."""
        cpu_val = 0.0 if cpu is None else cpu
        ram_val = 0.0 if memory is None else memory
        s_cpu = f"CPU {cpu_val:.0f}%" if cpu is not None else "CPU --%"
        s_ram = f"RAM {ram_val:.0f}%" if memory is not None else "RAM --%"

        w_cpu = get_text_width(self.font, s_cpu)
        w_ram = get_text_width(self.font, s_ram)

        draw.text((4 + (56 - w_cpu) // 2, 1), s_cpu, font=self.font, fill=0)
        draw.text((68 + (56 - w_ram) // 2, 1), s_ram, font=self.font, fill=0)

        draw_progress_bar(draw, 4, 12, 56, 7, cpu_val)
        draw_progress_bar(draw, 68, 12, 56, 7, ram_val)

        status = load_status(cpu, memory)
        draw.text((4, 20), status, font=self.font, fill=0)
        draw.text((109, 20), "2/3", font=self.font, fill=0)

    def render_page_3(self, draw, temp, fan_mode, fan_temp, fan_off_temp, fan_enabled=True):
        """Page 3: Temperature bar, threshold tick mark, and fan state."""
        temp_val = 30.0 if temp is None else temp
        s_temp = f"T:{temp_val:.1f}C" if temp is not None else "T:--.-C"

        if not fan_enabled:
            s_fan = "[NO FAN]"
        elif fan_mode == 1:
            s_fan = "[FAN ON]"
        elif fan_mode == 0:
            s_fan = "[FAN OFF]"
        else:
            s_fan = "[FAN --]"
        w_fan = get_text_width(self.font, s_fan)

        draw.text((4, 1), s_temp, font=self.font, fill=0)
        draw.text((124 - w_fan, 1), s_fan, font=self.font, fill=0)

        min_t, max_t = 30.0, 75.0
        pct = max(0.0, min(100.0, ((temp_val - min_t) / (max_t - min_t)) * 100.0))
        draw_progress_bar(draw, 4, 12, 120, 7, pct)

        if fan_enabled:
            thresh_pct = max(0.0, min(1.0, (fan_temp - min_t) / (max_t - min_t)))
            tick_x = int(round(4 + 2 + thresh_pct * (120 - 4)))
            draw.line([(tick_x, 10), (tick_x, 20)], fill=0, width=1)
            draw.text((4, 20), f"ON>={fan_temp:.0f}C OFF<{fan_off_temp:.0f}C", font=self.font, fill=0)
        else:
            draw.text((4, 20), "PASSIVE COOLING", font=self.font, fill=0)
        draw.text((109, 20), "3/3", font=self.font, fill=0)
