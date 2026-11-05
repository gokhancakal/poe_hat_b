#!/bin/bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo bash install.sh" >&2
    exit 1
fi
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP=/opt/poe-hat
SERVICE=/etc/systemd/system/poe-hat.service

# Install required packages I
apt update
apt install -y python3-pip python3-venv python3-dev build-essential libi2c-dev

# Prepare dependencies before replacing the running installation.
# Build at the final path: virtual environments cannot safely be relocated.
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
"$NEXT_VENV/bin/python3" -c 'import smbus, PIL, psutil'

# Copy required files; retain the source directory and user configuration.
for f in "$SOURCE_DIR"/*.py; do
    case "$(basename "$f")" in test_*|*_test.py) continue;; esac
    install -m 644 "$f" "$STAGE/"
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
"$NEXT_VENV/bin/python3" -m compileall -q "$STAGE"
rm -rf -- "$STAGE/__pycache__"

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
