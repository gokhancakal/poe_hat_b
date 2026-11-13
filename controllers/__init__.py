"""Fan controllers for PoE HAT and external setups."""
from .poe_fan import PoeFanController
from .dummy_fan import DummyFanController


def get_fan_controller(fan_type="poe", address=0x20):
    """Factory to get the appropriate fan controller based on hardware profile."""
    if str(fan_type).strip().lower() == "poe":
        return PoeFanController(address=address)
    return DummyFanController()


__all__ = ["PoeFanController", "DummyFanController", "get_fan_controller"]
