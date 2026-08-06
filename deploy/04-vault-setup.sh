#!/usr/bin/env bash
# Installs and configures a standalone HashiCorp Vault instance, loopback-only,
# to hold payment_server's Datamoll provider credentials (see
# admin/services/payment_server/vault.py). Does NOT run `vault operator
# init`/`unseal` or create the KV secret/policy/AppRole -- those happen once,
# interactively, after this script brings the service up sealed-but-running,
# so the unseal keys and root token can be handed to a human instead of
# written anywhere on disk.
set -euo pipefail

echo "=== HashiCorp apt repo ==="
apt-get update -y
apt-get install -y gnupg software-properties-common curl
curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/hashicorp.list
apt-get update -y
apt-get install -y vault

echo "=== dedicated low-privilege service user ==="
if ! id -u vault >/dev/null 2>&1; then
    useradd --system --home /opt/vault --shell /usr/sbin/nologin vault
fi
mkdir -p /opt/vault/data /etc/vault.d
chown -R vault:vault /opt/vault
chmod 750 /opt/vault/data

echo "=== vault config: loopback only, TLS terminated at nginx elsewhere ==="
cat > /etc/vault.d/vault.hcl <<'EOF'
ui = false

storage "file" {
  path = "/opt/vault/data"
}

listener "tcp" {
  address     = "127.0.0.1:8202"
  tls_disable = true
}

disable_mlock = false
api_addr      = "http://127.0.0.1:8202"
EOF
chown vault:vault /etc/vault.d/vault.hcl
chmod 640 /etc/vault.d/vault.hcl

echo "=== systemd unit ==="
cat > /etc/systemd/system/vault.service <<'EOF'
[Unit]
Description=HashiCorp Vault - payment_server secret storage
After=network.target

[Service]
Type=simple
User=vault
Group=vault
ExecStart=/usr/bin/vault server -config=/etc/vault.d/vault.hcl
Restart=on-failure
RestartSec=3
# Vault wants to mlock secret memory pages so they never hit swap; grant just
# that one capability instead of running as root.
AmbientCapabilities=CAP_IPC_LOCK
CapabilityBoundingSet=CAP_IPC_LOCK
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/vault/data
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now vault
sleep 2
echo "=== DONE: vault installed, running, SEALED (expected) ==="
VAULT_ADDR=http://127.0.0.1:8202 vault status || true
