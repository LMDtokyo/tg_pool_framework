#!/usr/bin/env bash
set -euo pipefail

echo "=== apt update/upgrade ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

echo "=== installing base packages ==="
apt-get install -y \
    git curl wget build-essential \
    python3-venv python3-pip python3-dev \
    nginx certbot python3-certbot-nginx \
    ufw fail2ban unattended-upgrades \
    postgresql postgresql-contrib \
    jq htop

echo "=== firewall: default deny, allow ssh/http/https only ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

echo "=== fail2ban for sshd ==="
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = 22
filter = sshd
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "=== unattended security upgrades ==="
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades

echo "=== dedicated low-privilege service user ==="
if ! id -u tgpool >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin --home-dir /opt/tgpool tgpool
fi
mkdir -p /opt/tgpool
chown tgpool:tgpool /opt/tgpool

echo "=== postgresql: enable + create databases/roles ==="
systemctl enable --now postgresql

echo "=== SSH hardening: key-only auth ==="
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh || systemctl reload sshd

echo "=== DONE: base setup complete ==="
python3 --version
nginx -v
psql --version
ufw status
fail2ban-client status sshd || true
