# /*****************************************************************************
# * | File        :   sh1106.py
# * | Function    :   SH1106 1.3inch OLED (128x64) 4-wire SPI Driver
# * | Info        :   Waveshare 1.3inch OLED HAT compatible
# ******************************************************************************/

import time

try:
    import spidev
except ImportError:
    spidev = None

try:
    import RPi.GPIO as GPIO
    _GPIO_LIB = "RPi.GPIO"
except (ImportError, RuntimeError):
    try:
        from gpiozero import OutputDevice
        _GPIO_LIB = "gpiozero"
    except ImportError:
        _GPIO_LIB = "mock"


class SH1106(object):
    """
    Driver for SH1106 1.3 inch OLED (128x64) via 4-wire SPI.
    Standard Waveshare 1.3inch OLED HAT pinout:
      - RST (Reset): GPIO 27 (Pin 13)
      - DC (Data/Command): GPIO 25 (Pin 22)
      - CS (Chip Select): GPIO 8 / CE0 (Pin 24)
      - DIN (MOSI): GPIO 10 (Pin 19)
      - CLK (SCLK): GPIO 11 (Pin 23)
    """
    def __init__(self, rst=27, dc=25, cs=8, spi_bus=0, spi_device=0, spi_freq=10000000):
        self.width = 128
        self.height = 64
        self.Column = 128
        self.Page = 8  # 64 / 8
        self.rst_pin = rst
        self.dc_pin = dc
        self.cs_pin = cs
        self.spi_bus_num = spi_bus
        self.spi_dev_num = spi_device
        self.spi_freq = spi_freq
        self.spi = None
        self._gpio_mode = _GPIO_LIB
        self._gpiozero_rst = None
        self._gpiozero_dc = None

        self._init_gpio()
        self._init_spi()

    def _init_gpio(self):
        gpio_error = None
        if self._gpio_mode == "RPi.GPIO":
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(self.rst_pin, GPIO.OUT)
                GPIO.setup(self.dc_pin, GPIO.OUT)
                return
            except Exception as error:
                gpio_error = error
                self._gpio_mode = "gpiozero"
        if self._gpio_mode == "gpiozero":
            try:
                from gpiozero import OutputDevice
                self._gpiozero_rst = OutputDevice(self.rst_pin, active_high=True, initial_value=True)
                self._gpiozero_dc = OutputDevice(self.dc_pin, active_high=True, initial_value=False)
                return
            except Exception as error:
                gpio_error = error
                self._gpio_mode = "mock"
        if self._gpio_mode == "mock":
            error = RuntimeError(
                "SH1106 requires working GPIO support (RPi.GPIO or gpiozero)"
            )
            if gpio_error is not None:
                raise error from gpio_error
            raise error

    def _init_spi(self):
        if spidev is None:
            raise RuntimeError("SH1106 requires the spidev package")
        self.spi = spidev.SpiDev()
        try:
            self.spi.open(self.spi_bus_num, self.spi_dev_num)
            self.spi.max_speed_hz = self.spi_freq
            self.spi.mode = 0b00
        except Exception:
            try:
                self.spi.close()
            except Exception:
                pass
            self.spi = None
            raise

    def _set_pin(self, pin_name, value):
        if self._gpio_mode == "RPi.GPIO":
            pin = self.rst_pin if pin_name == "rst" else self.dc_pin
            GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)
        elif self._gpio_mode == "gpiozero":
            dev = self._gpiozero_rst if pin_name == "rst" else self._gpiozero_dc
            if dev is not None:
                if value:
                    dev.on()
                else:
                    dev.off()

    def reset(self):
        """Hardware reset pulse for SH1106."""
        self._set_pin("rst", True)
        time.sleep(0.05)
        self._set_pin("rst", False)
        time.sleep(0.05)
        self._set_pin("rst", True)
        time.sleep(0.05)

    def SendCommand(self, cmd):
        """Send command byte to SH1106 (DC = 0)."""
        if self.spi is None:
            raise RuntimeError("SH1106 SPI device is not initialized")
        self._set_pin("dc", False)
        if isinstance(cmd, list):
            self.spi.writebytes(cmd)
        else:
            self.spi.writebytes([cmd])

    def SendData(self, data):
        """Send data byte or list of bytes to SH1106 (DC = 1)."""
        if self.spi is None:
            raise RuntimeError("SH1106 SPI device is not initialized")
        self._set_pin("dc", True)
        if isinstance(data, list):
            self.spi.writebytes(data)
        else:
            self.spi.writebytes([data])

    def set_contrast(self, contrast=50):
        val = max(1, min(255, int(contrast)))
        self.SendCommand(0x81)
        self.SendCommand(val)

    def sleep(self):
        self.SendCommand(0xAE)

    def wake(self):
        self.SendCommand(0xAF)

    def Init(self, contrast=50):
        """Initialize SH1106 128x64 display panel."""
        self.reset()

        self.SendCommand(0xAE)  # Turn display off

        self.SendCommand(0x02)  # Set lower column address (offset 2 for 128px screen on 132-col RAM)
        self.SendCommand(0x10)  # Set higher column address
        self.SendCommand(0x40)  # Set display start line address

        self.SendCommand(0xB0)  # Set page address
        self.set_contrast(contrast)

        self.SendCommand(0xA1)  # Set segment re-map (A1 = column 127 mapped to SEG0)
        self.SendCommand(0xA6)  # Set normal display (A6 = normal, A7 = inverse)
        self.SendCommand(0xA8)  # Set multiplex ratio
        self.SendCommand(0x3F)  # 1/64 duty (64 lines)

        self.SendCommand(0xAD)  # Set DC-DC enable
        self.SendCommand(0x8B)  # Built-in DC-DC on
        self.SendCommand(0x33)  # VPP = 9.0V

        self.SendCommand(0xC8)  # Set COM output scan direction (C8 = remapped mode)
        self.SendCommand(0xD3)  # Set display offset
        self.SendCommand(0x00)  # No offset

        self.SendCommand(0xD5)  # Set display clock divide ratio / oscillator freq
        self.SendCommand(0x80)  # Divide by 1, frequency = 0

        self.SendCommand(0xD9)  # Set pre-charge period
        self.SendCommand(0x1F)  # Dis-charge = 1 DCLK, Pre-charge = 15 DCLK

        self.SendCommand(0xDA)  # Set COM pins hardware configuration
        self.SendCommand(0x12)  # Alternative COM pin configuration

        self.SendCommand(0xDB)  # Set VCOMH deselect level
        self.SendCommand(0x40)  # ~0.83 x VCC

        self.SendCommand(0xAF)  # Turn display on

    def ClearBlack(self):
        """Clear entire display RAM to black."""
        for page in range(self.Page):
            self.SendCommand(0xB0 + page)
            self.SendCommand(0x02)  # SH1106 column start offset
            self.SendCommand(0x10)
            self.SendData([0x00] * self.Column)

    def ClearWhite(self):
        """Clear entire display RAM to white."""
        for page in range(self.Page):
            self.SendCommand(0xB0 + page)
            self.SendCommand(0x02)
            self.SendCommand(0x10)
            self.SendData([0xFF] * self.Column)

    def getbuffer(self, image):
        """
        Convert PIL Image to 1-bit monochrome byte buffer compatible with SH1106.
        Layout: 8 pages (rows of 8 vertical pixels each) x 128 columns.
        Uses same inversion as SSD1306 (white image = 0, black pixels lit).
        """
        buf = [0xFF] * (self.Page * self.Column)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()

        if imwidth == self.width and imheight == self.height:
            for y in range(imheight):
                for x in range(imwidth):
                    if pixels[x, y] == 0:
                        buf[x + int(y / 8) * self.width] &= ~(1 << (y % 8))
        elif imwidth == self.height and imheight == self.width:
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[(newx + int(newy / 8) * self.width)] &= ~(1 << (newy % 8))

        for x in range(self.Page * self.Column):
            buf[x] = (~buf[x]) & 0xFF

        return buf

    def ShowImage(self, pBuf):
        """
        Write image buffer to display RAM across 8 pages.
        Note: SH1106 RAM is 132x64, screen starts at column 2.
        """
        for page in range(self.Page):
            self.SendCommand(0xB0 + page)  # Page address
            self.SendCommand(0x02)         # Lower column address: offset 2
            self.SendCommand(0x10)         # Higher column address: 0
            page_data = pBuf[self.width * page : self.width * (page + 1)]
            self.SendData(page_data)

    def Closebus(self):
        """Release SPI and GPIO resources."""
        if self.spi is not None:
            try:
                self.spi.close()
            except Exception:
                pass
            self.spi = None

        if self._gpio_mode == "RPi.GPIO":
            try:
                GPIO.cleanup([self.rst_pin, self.dc_pin])
            except Exception:
                pass
        elif self._gpio_mode == "gpiozero":
            if self._gpiozero_rst:
                try:
                    self._gpiozero_rst.close()
                except Exception:
                    pass
                self._gpiozero_rst = None
            if self._gpiozero_dc:
                try:
                    self._gpiozero_dc.close()
                except Exception:
                    pass
                self._gpiozero_dc = None
