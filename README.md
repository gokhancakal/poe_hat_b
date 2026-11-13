
This installation is designed for **Power Over Ethernet HAT (Type B)** and **Waveshare 1.3inch OLED HAT** OLED display and fan control for Raspberry Pi OS & Ubuntu.

#### Hardware Profiles

- **Displays (`--display`):**
  - `poe`: 0.91" 128x32 SSD1306 OLED via I2C (default on PoE HAT B)
  - `waveshare-1.3`: 1.3" 128x64 SH1106 OLED via 4-wire SPI (Waveshare 1.3inch OLED HAT)
- **Fan Control (`--fan`):**
  - `poe`: I2C fan controller at address 0x20 (default on PoE HAT B)
  - `none`: Fan control disabled (use when running without PoE HAT or for passive cooling)

#### Enable Interfaces

1. **I2C Interface (required for `--display poe` and `--fan poe`):**
   ```sh
   sudo raspi-config nonint do_i2c 0
   ```
2. **SPI Interface (required for `--display waveshare-1.3`):**
   ```sh
   sudo raspi-config nonint do_spi 0
   ```
   *(Note: The installer automatically enables SPI if `--display waveshare-1.3` is selected).*

#### Waveshare 1.3" OLED Pin Connections (4-wire SPI)

| Pin Name | Physical Pin | BCM GPIO | Function |
|----------|--------------|----------|----------|
| **VCC**  | Pin 1 / 17   | 3.3V     | Power    |
| **GND**  | Pin 6 / 9    | GND      | Ground   |
| **DIN**  | Pin 19       | GPIO 10  | SPI0 MOSI|
| **CLK**  | Pin 23       | GPIO 11  | SPI0 SCLK|
| **CS**   | Pin 24       | GPIO 8   | SPI0 CE0 |
| **DC**   | Pin 22       | GPIO 25  | Data/Command |
| **RST**  | Pin 13       | GPIO 27  | Reset    |

*Note on Stacking: The PoE HAT (B) uses I2C-1 (GPIO 2, 3), while the 1.3" OLED uses SPI0 (GPIO 8, 10, 11) and GPIO 25/27. There are no electrical pin conflicts; both can be operated simultaneously with a 40-pin header extender or jumper wires.*

#### Installation

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
page_interval = 3
contrast = 50
pixel_shift = true
screen_timeout = 0
```

Defaults: fan ON at 43 C, OFF below 41 C, update every 1 second, page rotation every 3 seconds.
Between 41 and 43 C the previous state is retained. Startup requests fan ON (if fan enabled).
Missing configuration uses defaults; invalid configuration logs a warning and
uses defaults. Valid ranges: `0 <= fan_off_temp < fan_on_temp <= 85`,
`0.1 <= interval <= 10` seconds, `1 <= page_interval <= 60` seconds,
`1 <= contrast <= 255`, and `screen_timeout >= 0`. `pixel_shift` accepts
`true` or `false`. A positive screen timeout turns off the OLED while idle;
fan activity, temperatures at or above the fan-on threshold, and `SIGUSR1`
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

```
poe_hat_b/
├── drivers/                  # Hardware display drivers
│   ├── __init__.py           # Exports SSD1306, SH1106
│   ├── ssd1306.py            # 0.91" 128x32 I2C OLED driver
│   └── sh1106.py             # 1.3" 128x64 4-wire SPI OLED driver
├── controllers/              # Fan controllers
│   ├── __init__.py           # get_fan_controller factory
│   ├── poe_fan.py            # I2C PCF8574 fan controller (PoE HAT)
│   └── dummy_fan.py          # No-op fan controller (passive / none)
├── renderers/                # UI rendering engines
│   ├── __init__.py           # View renderers and drawing helpers
│   ├── common.py             # Progress bars, geometric primitives, metrics
│   ├── view_128x32.py        # 128x32 3-page layout
│   └── view_128x64.py        # 128x64 3-page layout
├── util.py                   # System metrics, hardware coordinator
├── main.py                   # Service entry point & config loader
├── install.sh                # Deployment and systemd installer script
├── test_poe.py               # Automated unit test suite
├── config.ini.example        # Configuration template
└── README.md
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
