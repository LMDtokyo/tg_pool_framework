#!/usr/bin/env bash
set -euo pipefail

VENV=/opt/tgpool/venv/bin
SVC=/opt/tgpool/services

write_unit() {
    local name="$1" workdir="$2" envfile="$3" exec="$4"
    cat > "/etc/systemd/system/${name}.service" <<UNIT
[Unit]
Description=TG Pool admin platform - ${name}
After=network.target postgresql.service

[Service]
Type=simple
User=tgpool
Group=tgpool
WorkingDirectory=${workdir}
Environment=PYTHONPATH=${SVC}
EnvironmentFile=${envfile}
ExecStart=${exec}
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/tgpool/data
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
}

write_unit "license-public" "$SVC" "$SVC/license_server/.env" \
    "$VENV/uvicorn license_server.public_app:app --host 127.0.0.1 --port 8100 --no-access-log"

write_unit "license-admin" "$SVC" "$SVC/license_server/.env" \
    "$VENV/uvicorn license_server.admin_app:app --host 127.0.0.1 --port 8110 --no-access-log"

write_unit "payment-public" "$SVC" "$SVC/payment_server/.env" \
    "$VENV/uvicorn payment_server.public_app:app --host 127.0.0.1 --port 8200 --no-access-log"

write_unit "payment-admin" "$SVC" "$SVC/payment_server/.env" \
    "$VENV/uvicorn payment_server.admin_app:app --host 127.0.0.1 --port 8210 --no-access-log"

write_unit "payment-webhook" "$SVC" "$SVC/payment_server/.env" \
    "$VENV/uvicorn payment_server.webhook_app:app --host 127.0.0.1 --port 8220 --no-access-log"

write_unit "payment-signer" "$SVC" "$SVC/payment_signer/.env" \
    "$VENV/uvicorn payment_signer.app:app --host 127.0.0.1 --port 8300 --no-access-log"

write_unit "payment-deposit-watcher" "$SVC" "$SVC/payment_server/.env" \
    "$VENV/python -m payment_server.deposit_watcher"

systemctl daemon-reload
echo "UNITS_WRITTEN"
