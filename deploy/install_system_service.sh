#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root from project dir: sudo bash deploy/install_system_service.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found in PATH"
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/server.py" ]]; then
  echo "Could not find server.py at: ${PROJECT_DIR}/server.py"
  echo "Run this script from the drinks_tab project directory."
  exit 1
fi

# Run service as the normal login user (not root, no dedicated service user).
APP_USER="${SUDO_USER:-$(logname)}"
APP_GROUP="${APP_USER}"
SERVICE_PATH="/etc/systemd/system/croc-drinks-tab.service"

cat > "${SERVICE_PATH}" <<SERVICE
[Unit]
Description=CRoC Drinks Tab Server
After=local-fs.target
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON_BIN} ${PROJECT_DIR}/server.py
Restart=always
RestartSec=5
TimeoutStopSec=10
Environment=PYTHONUNBUFFERED=1
Environment=HOME=/home/${APP_USER}

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable --now croc-drinks-tab.service

echo
echo "Installed system service: ${SERVICE_PATH}"
echo "Runs as user: ${APP_USER}"
echo "Working directory: ${PROJECT_DIR}"
echo
echo "Useful commands:"
echo "  sudo systemctl status croc-drinks-tab.service"
echo "  sudo systemctl restart croc-drinks-tab.service"
echo "  sudo journalctl -u croc-drinks-tab.service -f"

sleep 1
echo
if command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8000/api/members >/dev/null 2>&1; then
  echo "Health check passed: http://127.0.0.1:8000/api/members reachable"
else
  echo "Health check failed: service started but endpoint is not reachable yet."
  echo "Inspect logs:"
  echo "  sudo systemctl status croc-drinks-tab.service --no-pager -l"
  echo "  sudo journalctl -u croc-drinks-tab.service -n 120 --no-pager"
fi
