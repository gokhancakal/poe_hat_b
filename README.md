
This installation is designed for **Power Over Ethernet HAT (Type B)** and **Waveshare 1.3inch OLED HAT** OLED display and fan control for Raspberry Pi OS & Ubuntu.

#### Hardware Profiles

- **Displays (`--display`):**
  - `poe`: 0.91" 128x32 SSD1306 OLED via I2C (default on PoE HAT B)
  - `waveshare-1.3`: 1.3" 128x64 SH1106 OLED via 4-wire SPI (Waveshare 1.3inch OLED HAT)
- **Fan Control (`--fan`):**
  - `poe`: I2C fan controller at address 0x20 (default on PoE HAT B)
  - `none`: Fan control disabled (use when running without PoE HAT or for passive cooling)

#### Enable Interfaces

I2C is required for `--display poe` and `--fan poe`. SPI is required for
`--display waveshare-1.3`.

**Using the raspi-config menu (Raspberry Pi OS):**

1. Install and open raspi-config:
   ```sh
   sudo apt-get update
   sudo apt-get install raspi-config
   sudo raspi-config
   ```
2. Select **Interface Options** (or **Interfacing Options** on older releases),
   then **I2C**, and enable it. Enable **SPI** here too if using the
   `waveshare-1.3` display.
3. Finish and reboot if prompted.

**Using commands (Raspberry Pi OS):**

Run the command(s) for the interface(s) used:

1. **I2C:**
   ```sh
   sudo raspi-config nonint do_i2c 0
   ```
2. **SPI:**
   ```sh
   sudo raspi-config nonint do_spi 0
   ```
The installer also attempts to enable SPI when `--display waveshare-1.3` is
selected. A reboot may be required before the interfaces become available.

#### Waveshare 1.3" OLED Pin Connections (4-wire SPI)

| Pin Name | Physical Pin | BCM GPIO | Function |
|----------|--------------|----------|----------|
| **VCC**  | Pin 1 / 17   | 3.3V     | Power    |
| **GND**  | Pin 6 / 9    | GND      | Ground   |
| **DIN**  | Pin 19       | GPIO 10  | SPI0 MOSI|
| **CLK**  | Pin 23       | GPIO 11  | SPI0 SCLK|
| **CS**   | Pin 24       | GPIO 8   | SPI0 CE0 |
| **DC**   | Pin 18       | GPIO 24  | Data/Command |
| **RST**  | Pin 22       | GPIO 25  | Reset    |

*Note on Stacking: The PoE HAT (B) uses I2C-1 (GPIO 2, 3), while the 1.3" OLED uses SPI0 (GPIO 8, 10, 11) and GPIO 24/25. There are no electrical pin conflicts; both can be operated simultaneously with a 40-pin header extender or jumper wires.*

#### Installation

Download and extract the source on the Raspberry Pi:

```sh
sudo apt-get update
sudo apt-get install wget unzip -y
wget https://github.com/gokhancakal/poe_hat_b/archive/refs/heads/master.zip
unzip -o master.zip -d .
cd poe_hat_b-master
```

Then install the default PoE HAT B setup, or choose a display and fan profile:

```sh
# 1. Standard PoE HAT (B) installation (Default: 0.91" OLED + PoE Fan)
sudo bash install.sh

# 2. Waveshare 1.3" OLED + PoE HAT Fan
sudo bash install.sh --display waveshare-1.3 --fan poe

# 3. Waveshare 1.3" OLED without PoE HAT (Pi only / Passive cooling)
sudo bash install.sh --display waveshare-1.3 --fan none
```

#### Resources

1. [Waveshare PoE HAT (B)](https://www.waveshare.com/wiki/PoE_HAT_(B))
2. [Waveshare 1.3inch OLED HAT](https://www.waveshare.com/wiki/1.3inch_OLED_HAT)

#### Configuration and operation

Edit `/opt/poe-hat/config.ini`, then run `sudo systemctl restart poe-hat`.
```ini
[poe]
# Display: 'poe' (128x32 I2C) or 'waveshare-1.3' (128x64 SPI)
display = poe
# Fan: 'poe' (I2C 0x20) or 'none' (disabled)
fan = poe
# Fan ON/OFF temperatures (C)
fan_on_temp = 43
fan_off_temp = 41
interval = 1
page_interval = 5
contrast = 50
pixel_shift = true
screen_timeout = 0
```

Defaults: fan ON at 43 C, OFF below 41 C, update every 1 second, page rotation every 5 seconds.
Between 41 and 43 C the previous state is retained. Startup requests fan ON (if fan enabled).
Missing configuration uses defaults. Invalid individual settings log a warning
and fall back independently, preserving valid hardware profiles and other settings.
An invalid fan threshold pair falls back together to 43/41 C. Unreadable or
syntactically malformed configuration uses the full defaults. Valid ranges: `0 <= fan_off_temp < fan_on_temp <= 85`,
`0.1 <= interval <= 10` seconds, `1 <= page_interval <= 60` seconds,
`1 <= contrast <= 255`, and `screen_timeout >= 0`. `pixel_shift` accepts
`true` or `false`. A positive screen timeout turns off the OLED while idle;
on the PoE display profile, fan start, crossing the fan-on threshold, and `SIGUSR1`
wake it (the signal keeps it awake for 60 seconds). Pixel shifting moves each
page by one pixel to reduce static-image retention.

The display rotates between three clean, icon-free screens:
- **128x32 Mode (PoE display):**
  - Page 1: IP address, Hostname, and Uptime (column-aligned).
  - Page 2: CPU and RAM percentage with dual symmetric 56px progress bars.
  - Page 3: Temperature, Fan status, full 120px thermal bar with 43 C threshold marker, and hysteresis limits.
- **128x64 Mode (Waveshare 1.3" display):**
  - Page 1: IP, Hostname, Uptime, OS, and status.
  - Page 2: Stacked full-width 120px progress bars for CPU and RAM with percentage indicators.
  - Page 3: Temperature, 120px thermal bar with threshold tick, and fan parameters or passive cooling info.
`--` means unavailable. FAN ON/OFF indicates the last successful command,
not measured rotation. Network/OLED errors do not stop temperature control.
OLED initialization is retried after 30 seconds. A temperature read failure
requests fan ON. An I2C failure cannot guarantee fan operation.
On SIGTERM or Ctrl+C, the application requests fan ON and closes both buses.
The first CPU sample is displayed as `--`.

```sh
sudo systemctl status poe-hat --no-pager
sudo journalctl -u poe-hat -n 50 --no-pager
sudo journalctl -u poe-hat -f
sudo systemctl restart poe-hat
```

Run installation from the extracted source with `sudo bash install.sh`.
The installer preserves the source and existing config, prepares dependencies
before stopping the service, and retains `/opt/poe-hat.previous` plus the previous
service file for manual recovery. Each installation has its own explicitly
addressed `/opt/python_poe.*` virtual environment; old environments are retained
for recovery. Remove unused ones only after checking current and previous
service `ExecStart` paths. The original `/opt/python_poe` is also retained.

The service runs as root; deployed source/config files are root-owned and
not writable by ordinary users. I2C must already be enabled and `/dev/i2c-1`
available. Raspberry Pi model and Ubuntu release compatibility must be checked
on the target device; this update has not been hardware-tested. `raspi-config`
availability and I2C setup steps can differ by distribution.

#### Architecture & Folder Structure

The project is structured into clean, modular packages:

```text
poe_hat_b/
|-- drivers/                  # Hardware display drivers
|   |-- __init__.py           # Exports SSD1306, SH1106
|   |-- ssd1306.py            # 0.91" 128x32 I2C OLED driver
|   `-- sh1106.py             # 1.3" 128x64 4-wire SPI OLED driver
|-- controllers/              # Fan controllers
|   |-- __init__.py           # get_fan_controller factory
|   |-- poe_fan.py            # I2C PCF8574 fan controller (PoE HAT)
|   `-- dummy_fan.py          # No-op fan controller (passive / none)
|-- renderers/                # OLED page renderers
|   |-- __init__.py           # View renderers and drawing helpers
|   |-- common.py             # Progress bars, text fitting, load status
|   |-- view_128x32.py        # 128x32 three-page layout
|   `-- view_128x64.py        # 128x64 three-page layout
|-- buttons.py                # OLED HAT GPIO buttons and event queue
|-- util.py                   # System metrics and hardware coordinator
|-- main.py                   # Service entry point and config loader
|-- install.sh                # Deployment and systemd installer
|-- test_poe.py               # Automated test suite
|-- config.ini.example        # Configuration template
`-- README.md
```

#### Validation

```sh
python3 -m unittest test_poe -v
bash -n install.sh
```

Tests simulate I2C; install Pillow and psutil in the test environment.
On the actual Pi also verify boot, no network route, OLED failure/recovery,
fan thresholds, service stop/restart, and repeat installation preserving config.
`is-active` immediately after installation is only a process-state check.

#### Uninstall

```sh
sudo systemctl disable --now poe-hat.service
sudo rm -f /etc/systemd/system/poe-hat.service
sudo systemctl daemon-reload
sudo rm -rf /opt/poe-hat
```

Stopping the service requests fan ON. Remove the previous installation/service
and unused virtual environments separately after checking their paths.

#### Waveshare OLED buttons and sleep

New Waveshare installations use `screen_timeout = 60`; the PoE default stays 0.
Explicit existing values (including 0) are preserved. With a positive timeout,
Waveshare starts awake and sleeps after that many seconds since the last button
press. Fan/temperature changes and page rotation never wake it or extend the timer.
Fan control continues during sleep. The first press while asleep only wakes it.

KEY1 selects network/system, KEY2 CPU/RAM, KEY3 temperature/fan. Joystick left/right
selects previous/next page, up/down changes contrast through 10, 25, 50, 75, 100,
and center immediately sleeps. Brightness changes stay in memory only. Manual
page selection pauses rotation until the next wake; pixel shifting continues on
manual pages. Configured contrast and pixel shifting are otherwise retained.
SIGUSR1 remains available for a timed 60-second wake.

BCM pins from the [official OLED HAT pinout](https://www.waveshare.com/wiki/1.3inch_OLED_HAT):
KEY1=21, KEY2=20, KEY3=16; up=6, down=19, left=5, right=26, center=13.
OLED DC=24 and RST=25 (LCD HAT wiring differs). Inputs use gpiozero/lgpio,
pull-ups and 50 ms debounce, with one event per press (no hold repeat). Callbacks
only enqueue events; the main loop processes them about every 50 ms without
increasing the fan/temperature sampling rate. GPIO initialization failure is
logged and disables buttons without stopping fan control.

To explicitly migrate an existing Waveshare configuration from timeout 0 to 60:

```sh
sudo python3 - <<'PY'
import configparser
from pathlib import Path
path = Path('/opt/poe-hat/config.ini')
cfg = configparser.ConfigParser()
cfg.read(path)
if cfg.get('poe', 'display', fallback='poe') != 'waveshare-1.3':
    raise SystemExit('Expected waveshare-1.3 display profile')
cfg.set('poe', 'screen_timeout', '60')
with path.open('w') as target:
    cfg.write(target)
PY
sudo systemctl restart poe-hat
```

Tests mock GPIO and displays. Physical button debounce, boot behavior, SPI output
and simultaneous fan operation still require testing on the Raspberry Pi.

CPU/RAM are sampled at `interval` independently of the visible page and sleep.
Unavailable metrics display `LOAD UNKNOWN`; `IP AVAILABLE` means a local source
address was found, not that internet connectivity was verified. Long hostname
and uptime text is shortened with `~` to fit the screen. Brightness buttons stop
at the available steps; an explicit configured value outside 10–100 is retained
when there is no step in the requested direction.
Waveshare installation requires gpiozero/lgpio and reports installation failures
before replacing the running service. RPi.GPIO remains an optional display backend.

For the virtual-pin integration test, install `gpiozero` in the test environment.
It checks real Button press/hold/release handling; electrical bounce filtering
still needs a hardware test (gpiozero MockPin does not implement debounce).

Display page/shift timers run independently of the measurement interval on
Waveshare, and SIGUSR1 redraws on wake without taking an extra measurement.
A failed sleep command is retried after 30 seconds while fan sampling continues.
Installer profile precedence is explicit CLI options, installed config, source
config, then defaults; the selected config is also used when staging settings.
