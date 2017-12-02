#!/bin/bash

echo "Installing pylarexx in /usr/local/pylarexx"
mkdir -p /usr/local/pylarexx
cp -r pylarexx.py datalogger /usr/local/pylarexx
echo "Placing example config to /etc/pylarexx.yml"
cp example_pylarexx.yml /etc/pylarexx.yml
if [ -f /usr/bin/systemctl ] ; then
  echo "Creating pylarexx systemd service. Start it with: systemctl start pylarexx"
  echo "Start at boot with: systemctl enable pylarexx"
  cp systemd/pylarexx.service /etc/systemd/system
  systemctl daemon-reload
fi
