"""Waveshare OLED HAT inputs; callbacks only enqueue press events."""
from queue import SimpleQueue

# BCM numbering, https://www.waveshare.com/wiki/1.3inch_OLED_HAT
PINS = {'key1': 21, 'key2': 20, 'key3': 16, 'up': 6,
        'down': 19, 'left': 5, 'right': 26, 'center': 13}


class OLEDButtons:
    def __init__(self):
        self.events = SimpleQueue()
        self.devices = []
        self.factory = None
        try:
            from gpiozero import Button
            from gpiozero.pins.lgpio import LGPIOFactory
            self.factory = LGPIOFactory()
            for action, pin in PINS.items():
                button = Button(pin, pull_up=True, bounce_time=0.05,
                                pin_factory=self.factory)
                self.devices.append(button)
                button.when_pressed = lambda action=action: self.events.put(action)
        except Exception:
            self.close()
            raise

    def close(self):
        for button in self.devices:
            button.close()
        self.devices.clear()
        if self.factory is not None:
            self.factory.close()
            self.factory = None
