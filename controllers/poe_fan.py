"""PoE HAT Fan Controller using I2C (PCF8574 at default 0x20)."""
import logging
import smbus


class PoeFanController:
    """Controls the cooling fan on the Waveshare PoE HAT (B)."""
    def __init__(self, address=0x20, bus_num=1):
        self.enabled = True
        self.address = address
        self.bus_num = bus_num
        self.i2c = smbus.SMBus(self.bus_num)
        self.fan_mode = None
        try:
            self.fan_on()
        except OSError:
            if self.i2c is not None:
                self.i2c.close()
                self.i2c = None
            raise

    def fan_on(self):
        """Turn on the fan (bit 0 cleared to 0 on PCF8574)."""
        if self.i2c is None:
            return
        if self.fan_mode != 1:
            current = self.i2c.read_byte(self.address)
            self.i2c.write_byte(self.address, 0xFE & current)
            self.fan_mode = 1
            logging.info("Fan ON")

    def fan_off(self):
        """Turn off the fan (bit 0 set to 1 on PCF8574)."""
        if self.i2c is None:
            return
        if self.fan_mode != 0:
            current = self.i2c.read_byte(self.address)
            self.i2c.write_byte(self.address, 0x01 | current)
            self.fan_mode = 0
            logging.info("Fan OFF")

    def update(self, temp, fan_temp, fan_off_temp):
        """Update fan state according to temperature and hysteresis thresholds."""
        if temp is None or temp >= fan_temp:
            self.fan_on()
        elif temp < fan_off_temp:
            self.fan_off()
        elif self.fan_mode is None:
            self.fan_on()
        return self.fan_mode

    def close(self):
        """Failsafe: Leave fan ON before closing I2C bus."""
        try:
            self.fan_on()
        except OSError as error:
            self.fan_mode = None
            logging.warning("Failed to set fan ON during shutdown: %s", error)
        finally:
            if self.i2c is not None:
                try:
                    self.i2c.close()
                except Exception:
                    pass
                self.i2c = None
