# CRoC Drinks Tab

Simple localhost web app for tracking student drinks balances.

## What It Does

Members can:
- Search by name or student number.
- Use the always-on webcam barcode scanner to populate or replace the search from student or staff IDs.
- Clear the search with one button.
- Buy one drink from their balance.

Admins can:
- Unlock the admin panel with the password.
- Add, edit, and remove members.
- Adjust balances.
- Update the drink price.
- Export and import the member list as CSV.

## Files

- `server.py` - local Python server and SQLite API
- `croc_drinks_tab.html` - single-page frontend
- `vendor/zxing-browser.min.js` - bundled offline barcode decoder fallback
- `drinks_tab.db` - local SQLite database, created automatically
- `deploy/croc-drinks-tab.service` - systemd service file
- `deploy/install_system_service.sh` - helper to install the service

## Requirements

- Ubuntu laptop or desktop
- `python3`
- A Chromium-based browser on Ubuntu
- Webcam access enabled in the browser

The barcode scanner uses the browser's built-in `BarcodeDetector` API when available and falls back to a bundled offline decoder when it is not. It accepts IDs with 3 leading unused characters followed by either a 7-character or 8-character member ID.

## Quick Start

From this folder:

```bash
python3 server.py
```

Then open:

- <http://127.0.0.1:8000>

On first use, allow webcam access in the browser so the always-on scanner can start.

## Recommended Deployment

Install the app as a systemd service so it starts on boot:

```bash
cd /absolute/path/to/drinks_tab
sudo bash deploy/install_system_service.sh
```

Useful service commands:

```bash
sudo systemctl start croc-drinks-tab.service
sudo systemctl stop croc-drinks-tab.service
sudo systemctl restart croc-drinks-tab.service
sudo systemctl status croc-drinks-tab.service
```

To follow logs:

```bash
sudo journalctl -u croc-drinks-tab.service -f
```

## First-Time Setup Checklist

1. Copy this folder onto the Ubuntu machine.
2. Run the systemd install script.
3. Start the service.
4. Open the app in Chrome or Chromium.
5. Allow webcam access.
6. Unlock the admin panel.
7. Import the member CSV or add members manually.
8. Confirm the scanner reads a student card and fills the search.

## Data

- Member data is stored in `./drinks_tab.db`
- Member activity is logged in the SQLite table `member_audit_log`

To inspect the latest activity:

```bash
sqlite3 ./drinks_tab.db \
"SELECT datetime(event_time_ms/1000,'unixepoch','localtime'), action, actor, member_name, balance_before, balance_after, balance_delta FROM member_audit_log ORDER BY id DESC LIMIT 20;"
```

## Troubleshooting

If the page loads but scanning does not work:
- Use Chrome or Chromium on Ubuntu.
- Check that webcam permission is allowed.
- Confirm no other app is using the webcam.
- Reload the page.

If the frontend cannot connect:

```bash
curl http://127.0.0.1:8000/api/members
sudo systemctl status croc-drinks-tab.service --no-pager -l
sudo journalctl -u croc-drinks-tab.service -n 120 --no-pager
```
