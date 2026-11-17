import time
import logging
import signal
import configparser
import math
from pathlib import Path
import util


def load_config():
    defaults = ('poe', 'poe', 43.0, 41.0, 1.0, 5.0, 50, True, 0.0)
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
    except FileNotFoundError:
        return defaults
    except (OSError, configparser.Error) as error:
        logging.warning('Unreadable config; using defaults: %s', error)
        return defaults

    def setting(name, getter, default, valid=lambda value: True):
        try:
            value = getter('poe', name, fallback=default)
            if not valid(value):
                raise ValueError('out of range')
            return value
        except (ValueError, configparser.Error) as error:
            logging.warning('Invalid %s; using %s: %s', name, default, error)
            return default

    on = setting('fan_on_temp', config.getfloat, 43.0,
                 lambda v: math.isfinite(v) and 0 < v <= 85)
    off = setting('fan_off_temp', config.getfloat, 41.0,
                  lambda v: math.isfinite(v) and 0 <= v < 85)
    if off >= on:
        logging.warning('Invalid fan threshold pair; using 43/41 C')
        on, off = 43.0, 41.0
    interval = setting('interval', config.getfloat, 1.0, lambda v: 0.1 <= v <= 10)
    page_interval = setting('page_interval', config.getfloat, 5.0, lambda v: 1 <= v <= 60)
    contrast = setting('contrast', config.getint, 50, lambda v: 1 <= v <= 255)
    pixel_shift = setting('pixel_shift', config.getboolean, True)
    timeout = setting('screen_timeout', config.getfloat,
                      60.0 if display == 'waveshare-1.3' else 0.0,
                      lambda v: math.isfinite(v) and v >= 0)
    return display, fan, on, off, interval, page_interval, contrast, pixel_shift, timeout


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
            next_sample = 0.0
            while running:
                started = time.monotonic()
                sample = started >= next_sample
                POE.poe_hat_display(fan_on_temp, fan_off_temp, page_interval, sample=sample)
                if sample:
                    next_sample = started + interval
                delay = 0.05 if display == "waveshare-1.3" else interval
                time.sleep(max(0, min(delay, next_sample - time.monotonic())))
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
