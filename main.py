import time
import logging
import signal
import configparser
import math
from pathlib import Path
import util


def load_config():
    defaults = (43.0, 41.0, 1.0, 3.0)
    config = configparser.ConfigParser()
    try:
        with Path(__file__).with_name('config.ini').open() as source:
            config.read_file(source)
        values = (config.getfloat('poe', 'fan_on_temp'),
                  config.getfloat('poe', 'fan_off_temp'),
                  config.getfloat('poe', 'interval'),
                  config.getfloat('poe', 'page_interval', fallback=3.0))
        on, off, interval, page_interval = values
        if not all(math.isfinite(value) for value in values):
            raise ValueError('Settings must be finite numbers')
        if not 0 <= off < on <= 85 or not 0.1 <= interval <= 10 or not 1 <= page_interval <= 60:
            raise ValueError('Invalid parameter range in config')
        return values
    except FileNotFoundError:
        return defaults
    except (OSError, ValueError, configparser.Error) as error:
        logging.warning('Invalid config; using defaults: %s', error)
        return defaults


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    fan_on_temp, fan_off_temp, interval, page_interval = load_config()
    logging.info("Config: fan_on=%.1f C, fan_off=%.1f C, interval=%.1f s, page_interval=%.1f s",
                 fan_on_temp, fan_off_temp, interval, page_interval)
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with util.PoeHatB() as POE:
        try:
            while running:
                started = time.monotonic()
                POE.poe_hat_display(fan_on_temp, fan_off_temp, page_interval)
                time.sleep(max(0, interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
