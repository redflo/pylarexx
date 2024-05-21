#!/bin/bash

echo "Installing pylarexx in /usr/local/pylarexx"
mkdir -p /usr/local/pylarexx
cp -r pylarexx.py deviceinfo.xml datalogger /usr/local/pylarexx
echo "Placing example config to /etc/pylarexx.yml"
cp example_pylarexx.yml /etc/pylarexx.yml
if [ -f /usr/bin/systemctl ] ; then
  echo "Add user pylarexx to run daemon"
  mkdir /var/run/pylarexx/
  useradd pylarexx --system --user-group --home-dir /var/run/pylarexx/
  echo "Install udev rule to allow daemon device access"
  cp etc/udev/rules.d/51-rf_usb.rules /etc/udev/rules.d/
  echo "Creating pylarexx systemd service. Start it with: systemctl start pylarexx"
  echo "Start at boot with: systemctl enable pylarexx"
  cp etc/systemd/pylarexx.service /etc/systemd/system
  systemctl daemon-reload
fi
