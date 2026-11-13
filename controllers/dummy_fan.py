"""Dummy fan controller for systems without PoE HAT fan hardware."""
import logging


class DummyFanController:
    """No-op fan controller used when fan=none is configured."""
    def __init__(self):
        self.enabled = False
        self.fan_mode = None
        logging.info("DummyFanController initialized (fan hardware disabled)")

    def fan_on(self):
        """No-op."""
        pass

    def fan_off(self):
        """No-op."""
        pass

    def update(self, temp, fan_temp, fan_off_temp):
        """No-op status update."""
        return None

    def close(self):
        """No-op cleanup."""
        pass
