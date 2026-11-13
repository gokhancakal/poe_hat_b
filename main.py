import time
import logging
import signal
import configparser
import math
from pathlib import Path
import util


def load_config():
    defaults = ('poe', 'poe', 43.0, 41.0, 1.0, 3.0, 50, True, 0.0)
    config = configparser.ConfigParser()
    try:
        with Path(__file__).with_name('config.ini').open() as source:
            config.read_file(source)
        display = config.get('poe', 'display', fallback='poe').strip().lower()
        fan = config.get('poe', 'fan', fallback='poe').strip().lower()
        if display not in ('poe', 'waveshare-1.3'):
            logging.warning("Unknown display '%s'; falling back to 'poe'", display)
            display = 'poe'
        if fan not in ('poe', 'none'):
            logging.warning("Unknown fan '%s'; falling back to 'poe'", fan)
            fan = 'poe'
        values = (config.getfloat('poe', 'fan_on_temp', fallback=43.0),
                  config.getfloat('poe', 'fan_off_temp', fallback=41.0),
                  config.getfloat('poe', 'interval', fallback=1.0),
                  config.getfloat('poe', 'page_interval', fallback=3.0),
                  config.getint('poe', 'contrast', fallback=50),
                  config.getfloat('poe', 'screen_timeout', fallback=0.0))
        on, off, interval, page_interval, contrast, screen_timeout = values
        if not all(math.isfinite(value) for value in values):
            raise ValueError('Settings must be finite numbers')
        pixel_shift = config.getboolean('poe', 'pixel_shift', fallback=True)
        if (not 0 <= off < on <= 85 or not 0.1 <= interval <= 10
                or not 1 <= page_interval <= 60 or not 1 <= contrast <= 255
                or screen_timeout < 0):
            raise ValueError('Invalid parameter range in config')
        return (display, fan, on, off, interval, page_interval,
                contrast, pixel_shift, screen_timeout)
    except FileNotFoundError:
        return defaults
    except (OSError, ValueError, configparser.Error) as error:
        logging.warning('Invalid config; using defaults: %s', error)
        return defaults


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    (display, fan, fan_on_temp, fan_off_temp, interval, page_interval,
     contrast, pixel_shift, screen_timeout) = load_config()
    logging.info(
        "Config: display=%s, fan=%s, fan_on=%.1f C, fan_off=%.1f C, "
        "interval=%.1f s, page_interval=%.1f s, contrast=%d, "
        "pixel_shift=%s, screen_timeout=%.1f s",
        display, fan, fan_on_temp, fan_off_temp, interval, page_interval,
        contrast, pixel_shift, screen_timeout)
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with util.PoeHatB(display_type=display, fan_type=fan, contrast=contrast,
                      pixel_shift=pixel_shift, screen_timeout=screen_timeout) as POE:
        if hasattr(signal, 'SIGUSR1'):
            def wake(signum, frame):
                POE.request_wake(60)

            signal.signal(signal.SIGUSR1, wake)
        try:
            while running:
                started = time.monotonic()
                POE.poe_hat_display(fan_on_temp, fan_off_temp, page_interval)
                time.sleep(max(0, interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
