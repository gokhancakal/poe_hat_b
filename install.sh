#!/bin/bash

# Install required packages I
apt update
apt install -y python3-pip python3-venv python3-pil libatlas-base-dev raspi-config

# Create and activate python venv
[ -d /opt/python_poe ] && rm -rf /opt/python_poe
python3 -m venv /opt/python_poe

# Install required packages II
source /opt/python_poe/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Move required files to poe-hat directory
[ -d /opt/poe-hat ] && rm -rf /opt/poe-hat
mkdir -p /opt/poe-hat
mv *.py /opt/poe-hat/
chmod 777 -R /opt/poe-hat

# Cleanup
cd ..
rm master.zip
rm -rf poe_hat_b-master

# Create/Activate service
[ -d /etc/systemd/system/poe-hat.service ] && rm -rf /etc/systemd/system/poe-hat.service

PYTHON=`which python3 |head -n1`

cat <<EOF >poe-hat.service
[Unit]
Description=Poe Hat B
After=network.target
[Service]
Environment=systemd=true
ExecStart=${PYTHON} /opt/poe-hat/main.py
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

mv -f poe-hat.service /etc/systemd/system

systemctl daemon-reload
systemctl enable poe-hat.service --now
systemctl restart poe-hat.service
systemctl status poe-hat.service