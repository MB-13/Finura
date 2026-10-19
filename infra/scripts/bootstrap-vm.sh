#!/usr/bin/env bash
# One-time setup of the Oracle Always Free ARM VM (Ubuntu 24.04). Run as the default `ubuntu` user.
# See docs/runbooks/oracle-vm-setup.md for the console steps that come first.
set -euo pipefail

sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get -y install unattended-upgrades fail2ban git htop netfilter-persistent
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# Oracle's Ubuntu images block 80/443 in iptables even when the security list allows them
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
done
sudo netfilter-persistent save

# 4 GB swap as a safety net for the 12 GB memory budget
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Docker
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
echo '{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

# keys-only SSH
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

mkdir -p ~/doctune/infra ~/backups
echo "Done. Log out and back in (docker group), copy infra/ to ~/doctune/infra, create .env from env.example."
