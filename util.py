import smbus
import psutil
import socket
from PIL import Image, ImageDraw
import SSD1306

show = SSD1306.SSD1306()
show.Init()
image1 = Image.new('1', (show.width, show.height), "WHITE")
draw = ImageDraw.Draw(image1)


class PoeHatB:
    def __init__(self, address=0x20):
        self.i2c = smbus.SMBus(1)
        self.address = address
        self.fan_on()
        self.fan_mode = 0

    def fan_on(self):
        self.i2c.write_byte(self.address, 0xFE & self.i2c.read_byte(self.address))

    def fan_off(self):
        self.i2c.write_byte(self.address, 0x01 | self.i2c.read_byte(self.address))

    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip

    def get_hostname(self):
        hostname = socket.gethostname()
        return hostname

    def get_memory(self):
        memory = psutil.virtual_memory()[2]
        return memory

    def get_cpu(self):
        cpu = psutil.cpu_percent(4)
        return cpu

    def get_temp(self):
        with open('/sys/class/thermal/thermal_zone0/temp', 'rt') as f:
            temp = (int)(f.read()) / 1000.0
        return temp

    def poe_hat_display(self, fan_temp):
        # show.Init()
        # show.ClearBlack()

        image1 = Image.new('1', (show.width, show.height), "WHITE")
        draw = ImageDraw.Draw(image1)
        ip = self.get_ip()
        temp = self.get_temp()
        hostname = self.get_hostname()
        memory = self.get_memory()
        cpu = self.get_cpu()

        draw.text((0, 1), 'IP:' + str(ip), fill=0)
        draw.text((0, 10), 'CPU:%' + str(cpu) + '   RAM:%' + str(memory), fill=0)
        draw.text((0, 20), 'TEMP:' + str(((int)(temp*10))/10.0), fill=0)

        if temp >= fan_temp:
            self.fan_mode = 1

        elif temp < fan_temp-2:
            self.fan_mode = 0

        if self.fan_mode == 1:
            draw.text((73, 20), 'FAN:ON', fill=0)
            self.fan_on()
        else:
            draw.text((73, 20), 'FAN:OFF', fill=0)
            self.fan_off()
        show.ShowImage(show.getbuffer(image1))
