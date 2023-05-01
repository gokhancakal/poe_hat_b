import time
import logging
from . import util

logging.basicConfig(level=logging.INFO)

POE = util.PoeHatB()

try:
    while 1:
        POE.poe_hat_display(43)
        time.sleep(1)

except KeyboardInterrupt:
    POE.fan_off()
