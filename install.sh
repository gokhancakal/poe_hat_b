#!/bin/bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo bash install.sh" >&2
    exit 1
fi

DISPLAY_TYPE="poe"
FAN_TYPE="poe"
EXPLICIT_DISPLAY=0
EXPLICIT_FAN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --display)
            if [[ $# -lt 2 ]]; then
                echo "Error: --display requires an argument (poe | waveshare-1.3)" >&2
                exit 1
            fi
            DISPLAY_TYPE="$2"
            EXPLICIT_DISPLAY=1
            shift 2
            ;;
        --fan)
            if [[ $# -lt 2 ]]; then
                echo "Error: --fan requires an argument (poe | none)" >&2
                exit 1
            fi
            FAN_TYPE="$2"
            EXPLICIT_FAN=1
            shift 2
            ;;
        -h|--help)
            echo "Usage: sudo bash install.sh [--display poe|waveshare-1.3] [--fan poe|none]"
            echo "  --display  Display hardware profile (default: poe)"
            echo "             poe           : 0.91\" 128x32 SSD1306 OLED (I2C)"
            echo "             waveshare-1.3 : 1.3\" 128x64 SH1106 OLED (4-wire SPI)"
            echo "  --fan      Fan control profile (default: poe)"
            echo "             poe           : Waveshare PoE HAT (B) I2C fan at 0x20"
            echo "             none          : Fan hardware disabled (passive cooling / no PoE HAT)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: sudo bash install.sh [--display poe|waveshare-1.3] [--fan poe|none]" >&2
            exit 1
            ;;
    esac
done

if [[ "$DISPLAY_TYPE" != "poe" && "$DISPLAY_TYPE" != "waveshare-1.3" ]]; then
    echo "Error: Invalid display '$DISPLAY_TYPE'. Must be 'poe' or 'waveshare-1.3'." >&2
    exit 1
fi
if [[ "$FAN_TYPE" != "poe" && "$FAN_TYPE" != "none" ]]; then
    echo "Error: Invalid fan '$FAN_TYPE'. Must be 'poe' or 'none'." >&2
    exit 1
fi

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP=/opt/poe-hat
SERVICE=/etc/systemd/system/poe-hat.service

# If not explicitly specified on CLI, preserve existing configuration if present
if [[ -f "$APP/config.ini" ]]; then
    if [[ $EXPLICIT_DISPLAY -eq 0 ]]; then
        PREV_DISP="$(grep -E "^[[:space:]]*display[[:space:]]*=" "$APP/config.ini" | cut -d= -f2 | cut -d'#' -f1 | cut -d';' -f1 | tr -d '[:space:]' || true)"
        if [[ "$PREV_DISP" == "waveshare-1.3" || "$PREV_DISP" == "poe" ]]; then
            DISPLAY_TYPE="$PREV_DISP"
        fi
    fi
    if [[ $EXPLICIT_FAN -eq 0 ]]; then
        PREV_FAN="$(grep -E "^[[:space:]]*fan[[:space:]]*=" "$APP/config.ini" | cut -d= -f2 | cut -d'#' -f1 | cut -d';' -f1 | tr -d '[:space:]' || true)"
        if [[ "$PREV_FAN" == "none" || "$PREV_FAN" == "poe" ]]; then
            FAN_TYPE="$PREV_FAN"
        fi
    fi
fi

echo "Installing with profiles: Display = $DISPLAY_TYPE | Fan = $FAN_TYPE"

NEEDS_REBOOT=0
if [[ "$DISPLAY_TYPE" == "waveshare-1.3" ]]; then
    # Enable SPI on Raspberry Pi
    if command -v raspi-config >/dev/null 2>&1; then
        raspi-config nonint do_spi 0 2>/dev/null || true
    fi
    for cfg in /boot/firmware/config.txt /boot/config.txt; do
        if [[ -f "$cfg" ]] && ! grep -q "^dtparam=spi=on" "$cfg"; then
            echo "dtparam=spi=on" >> "$cfg"
            NEEDS_REBOOT=1
        fi
    done
fi

# Install required packages
apt update
apt install -y python3-pip python3-venv python3-dev build-essential libi2c-dev

# Prepare dependencies before replacing the running installation.
NEXT_VENV="$(mktemp -d /opt/python_poe.XXXXXXXX)"
STAGE="$(mktemp -d /opt/poe-hat-stage.XXXXXXXX)"
committed=0
cleanup() {
    rm -rf -- "$STAGE"
    if [[ $committed -eq 0 ]]; then
        rm -rf -- "$NEXT_VENV"
    fi
}
trap cleanup EXIT
python3 -m venv "$NEXT_VENV"
"$NEXT_VENV/bin/python3" -m pip install -r "$SOURCE_DIR/requirements.txt"

if [[ "$DISPLAY_TYPE" == "waveshare-1.3" ]]; then
    "$NEXT_VENV/bin/python3" -m pip install spidev
    "$NEXT_VENV/bin/python3" -m pip install RPi.GPIO gpiozero lgpio 2>/dev/null || true
fi

"$NEXT_VENV/bin/python3" -c 'import PIL, psutil'
if [[ "$FAN_TYPE" == "poe" ]]; then
    "$NEXT_VENV/bin/python3" -c 'import smbus'
fi

# Copy required files; retain the source directory and user configuration.
for f in "$SOURCE_DIR"/*.py; do
    case "$(basename "$f")" in test_*|*_test.py) continue;; esac
    install -m 644 "$f" "$STAGE/"
done
for pkg in drivers controllers renderers; do
    if [[ -d "$SOURCE_DIR/$pkg" ]]; then
        install -d -m 755 "$STAGE/$pkg"
        install -m 644 "$SOURCE_DIR/$pkg"/*.py "$STAGE/$pkg/"
    fi
done
install -m 644 "$SOURCE_DIR/requirements.txt" "$STAGE/"

if [[ -f "$APP/config.ini" ]]; then
    install -m 644 "$APP/config.ini" "$STAGE/config.ini"
elif [[ -f "$SOURCE_DIR/config.ini" ]]; then
    install -m 644 "$SOURCE_DIR/config.ini" "$STAGE/config.ini"
elif [[ -f "$SOURCE_DIR/config.ini.example" ]]; then
    install -m 644 "$SOURCE_DIR/config.ini.example" "$STAGE/config.ini"
fi
if [[ -f "$SOURCE_DIR/config.ini.example" ]]; then
    install -m 644 "$SOURCE_DIR/config.ini.example" "$STAGE/config.ini.example"
fi

# Apply chosen display and fan options to staged config.ini
"$NEXT_VENV/bin/python3" -c "
import configparser
cfg = configparser.ConfigParser()
cfg.read('$STAGE/config.ini')
if not cfg.has_section('poe'):
    cfg.add_section('poe')
cfg.set('poe', 'display', '$DISPLAY_TYPE')
cfg.set('poe', 'fan', '$FAN_TYPE')
with open('$STAGE/config.ini', 'w') as f:
    cfg.write(f)
"

"$NEXT_VENV/bin/python3" -m compileall -q "$STAGE"
find "$STAGE" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

# Create/Activate service
cat > "$STAGE/poe-hat.service" <<EOF
[Unit]
Description=Poe Hat B
After=network.target
[Service]
Environment=systemd=true
ExecStart=$NEXT_VENV/bin/python3 $APP/main.py
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# Keep one previous installation for recovery.
systemctl stop poe-hat.service 2>/dev/null || true
if [[ -d "$APP" ]]; then
    rm -rf -- "$APP.previous"
    mv -- "$APP" "$APP.previous"
fi
install -d -o root -g root -m 755 "$APP"
install -o root -g root -m 644 "$STAGE"/*.py "$STAGE/config.ini" "$STAGE/requirements.txt" "$APP/"
for pkg in drivers controllers renderers; do
    if [[ -d "$STAGE/$pkg" ]]; then
        install -d -o root -g root -m 755 "$APP/$pkg"
        install -o root -g root -m 644 "$STAGE/$pkg"/*.py "$APP/$pkg/"
    fi
done
if [[ -f "$STAGE/config.ini.example" ]]; then
    install -o root -g root -m 644 "$STAGE/config.ini.example" "$APP/"
fi
if [[ -f "$SERVICE" ]]; then
    cp -p -- "$SERVICE" "$SERVICE.previous"
fi
install -o root -g root -m 644 "$STAGE/poe-hat.service" "$SERVICE"
committed=1
# Retain existing /opt/python_poe for compatibility; service uses its explicit venv.
systemctl daemon-reload
systemctl enable poe-hat.service
systemctl restart poe-hat.service
systemctl is-active --quiet poe-hat.service
systemctl status poe-hat.service --no-pager

if [[ "$NEEDS_REBOOT" -eq 1 ]]; then
    echo ""
    echo "======================================================================"
    echo ">>> NOTICE: SPI interface was enabled in boot configuration."
    echo ">>> A reboot is required for /dev/spidev0.0 to become active:"
    echo ">>>   sudo reboot"
    echo "======================================================================"
    echo ""
fi
