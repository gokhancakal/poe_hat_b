"""Renderer for 128x64 OLED display (SH1106 / Waveshare 1.3inch OLED)."""
from .common import draw_progress_bar, get_text_width


class View128x64:
    """Renders 3-page status views optimized for 128x64 OLED."""
    def __init__(self, font):
        self.font = font

    def render_page_1(self, draw, ip, hostname, uptime_str):
        """Page 1: Network & System Information."""
        draw.text((4, 4), "IP:", font=self.font, fill=0)
        draw.text((38, 4), str(ip), font=self.font, fill=0)

        draw.text((4, 16), "HOST:", font=self.font, fill=0)
        draw.text((38, 16), str(hostname), font=self.font, fill=0)

        draw.text((4, 28), "UP:", font=self.font, fill=0)
        draw.text((38, 28), str(uptime_str), font=self.font, fill=0)

        draw.text((4, 40), "OS:", font=self.font, fill=0)
        draw.text((38, 40), "LINUX / PI", font=self.font, fill=0)

        draw.text((4, 52), "STATUS: ONLINE", font=self.font, fill=0)
        draw.text((109, 52), "1/3", font=self.font, fill=0)

    def render_page_2(self, draw, cpu, memory):
        """Page 2: Full-width CPU and RAM progress bars."""
        cpu_val = 0.0 if cpu is None else cpu
        ram_val = 0.0 if memory is None else memory
        s_cpu = f"CPU: {cpu_val:.0f}%" if cpu is not None else "CPU: --%"
        s_ram = f"RAM: {ram_val:.0f}%" if memory is not None else "RAM: --%"

        draw.text((4, 4), s_cpu, font=self.font, fill=0)
        draw_progress_bar(draw, 4, 15, 120, 8, cpu_val)

        draw.text((4, 27), s_ram, font=self.font, fill=0)
        draw_progress_bar(draw, 4, 38, 120, 8, ram_val)

        status = "LOAD HIGH" if (cpu_val > 80 or ram_val > 85) else "LOAD NORMAL"
        draw.text((4, 52), status, font=self.font, fill=0)
        draw.text((109, 52), "2/3", font=self.font, fill=0)

    def render_page_3(self, draw, temp, fan_mode, fan_temp, fan_off_temp, fan_enabled=True):
        """Page 3: Thermal bar, threshold indicator, and fan operating mode."""
        temp_val = 30.0 if temp is None else temp
        s_temp = f"TEMP: {temp_val:.1f}C" if temp is not None else "TEMP: --.-C"

        if not fan_enabled:
            s_fan = "[NO FAN]"
        elif fan_mode == 1:
            s_fan = "[FAN ON]"
        elif fan_mode == 0:
            s_fan = "[FAN OFF]"
        else:
            s_fan = "[FAN --]"
        w_fan = get_text_width(self.font, s_fan)

        draw.text((4, 4), s_temp, font=self.font, fill=0)
        draw.text((124 - w_fan, 4), s_fan, font=self.font, fill=0)

        min_t, max_t = 30.0, 75.0
        pct = max(0.0, min(100.0, ((temp_val - min_t) / (max_t - min_t)) * 100.0))
        draw_progress_bar(draw, 4, 15, 120, 8, pct)

        if fan_enabled:
            thresh_pct = max(0.0, min(1.0, (fan_temp - min_t) / (max_t - min_t)))
            tick_x = int(round(4 + 2 + thresh_pct * (120 - 4)))
            draw.line([(tick_x, 13), (tick_x, 24)], fill=0, width=1)

            draw.text((4, 27), f"FAN ON  : >= {fan_temp:.0f}C", font=self.font, fill=0)
            draw.text((4, 39), f"FAN OFF : <  {fan_off_temp:.0f}C", font=self.font, fill=0)
            draw.text((4, 52), "FAN: ACTIVE", font=self.font, fill=0)
        else:
            draw.text((4, 27), "FAN HARDWARE : NONE", font=self.font, fill=0)
            draw.text((4, 39), "MODE: MONITOR ONLY", font=self.font, fill=0)
            draw.text((4, 52), "COOLING: PASSIVE", font=self.font, fill=0)

        draw.text((109, 52), "3/3", font=self.font, fill=0)
