
This installation is designed for **Power Over Ethernet HAT (Type B)** OLED and FAN control for Ubuntu OS.

For installation you must run the following commands.

#### Enable I2C Interface

1. Run this command:
   ```sh
   sudo apt-get install raspi-config
   sudo raspi-config
   ```
2. Select Interfacing Options > I2C.
3. Select Yes when prompted to enable the I2C interface.
4. Select Yes when prompted to automatically load the I2C kernel module.
5. Select Finish.
6. Select Yes when prompted to reboot.

#### Installation

<!--sec data-title="List files and directories: OS X and Linux" data-id="OSX_Linux_ls" data-collapse=true ces-->
    sudo apt install wget unzip -y \
    && sudo wget https://github.com/gokhancakal/poe_hat_b/archive/refs/heads/master.zip \
    && sudo unzip -o  master.zip -d . \
    && cd poe_hat_b-master \
    && sudo chmod +x install.sh \
    && sudo ./install.sh
<!--endsec-->

#### Resources

1.  [waveshare PoE HAT (B)](https://www.waveshare.com/wiki/PoE_HAT_(B))

#### Configuration and operation

Edit `/opt/poe-hat/config.ini`, then run `sudo systemctl restart poe-hat`.
Defaults: fan ON at 43 C, OFF below 41 C, update every 1 second, page rotation every 3 seconds.
Between 41 and 43 C the previous state is retained. Startup requests fan ON.
Missing configuration uses defaults; invalid configuration logs a warning and
uses defaults. Valid ranges: `0 <= fan_off_temp < fan_on_temp <= 85`,
`0.1 <= interval <= 10` seconds, and `1 <= page_interval <= 60` seconds.

The display rotates between three clean, icon-free screens:
- Page 1: IP address, Hostname, and Uptime (column-aligned).
- Page 2: CPU and RAM percentage with dual symmetric 56px progress bars.
- Page 3: Temperature, Fan status, full 120px thermal bar with 43 C threshold marker, and hysteresis limits.
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
