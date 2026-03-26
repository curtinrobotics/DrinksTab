# CRoC Drinks Tab

Simple localhost web app for drinks balances.

## What members can do
- Search by name or student number.
- Scan a barcode with a physical scanner into the search bar.
- Search accepts scanner values with a 3-character prefix before the stored student number.
- Clear the search with one button.
- Buy one drink (`-$1.00`) from their balance.
- Student numbers are searchable but hidden in the public members table.

## What admin can do
- Add members.
- Remove members.
- Search and select a member to edit.
- Update name and student number.
- Add/subtract from existing balance.
- Update the drink price.
- Admin auto-locks when switching back to the Members tab.
- Export current members database to CSV.
- Initialize/replace database from exported CSV.

## Local run (manual)
From this folder:

```bash
python3 server.py
```

Open:
- <http://127.0.0.1:8000>

The Members search box is designed for a keyboard-wedge barcode scanner. It stays focused, accepts scanned values like `xxx12345678`, strips the 3-character prefix for matching, allows normal keyboard typing, and auto-clears after 1 minute.

Database file is local SQLite at:
- `./drinks_tab.db`

All member changes are logged in:
- `member_audit_log` table (add/edit/purchase/remove/balance changes)

## Ubuntu auto-start on boot (recommended)
Install as a system service:

```bash
cd /absolute/path/to/drinks_tab
sudo bash deploy/install_system_service.sh
```

If you previously installed an older unit file, reinstall to overwrite it:

```bash
sudo systemctl disable --now croc-drinks-tab.service
cd /absolute/path/to/drinks_tab
sudo bash deploy/install_system_service.sh
```

Service commands:

```bash
sudo systemctl start croc-drinks-tab.service
sudo systemctl stop croc-drinks-tab.service
sudo systemctl restart croc-drinks-tab.service
sudo systemctl status croc-drinks-tab.service
sudo journalctl -u croc-drinks-tab.service -f
```

Disable auto-start:

```bash
sudo systemctl disable croc-drinks-tab.service
```

If the service shows running but frontend cannot connect, verify on the laptop:

```bash
curl -v http://127.0.0.1:8000/api/members
sudo systemctl status croc-drinks-tab.service --no-pager -l
sudo journalctl -u croc-drinks-tab.service -n 120 --no-pager
```

## Logs
Runtime/service logs (server stdout/stderr) are in systemd journal:

```bash
sudo journalctl -u croc-drinks-tab.service
sudo journalctl -u croc-drinks-tab.service -f
```

Member activity logs (add/edit/purchase/remove/balance changes) are stored in SQLite table `member_audit_log` inside `./drinks_tab.db`.

Example query:

```bash
sqlite3 ./drinks_tab.db \
"SELECT datetime(event_time_ms/1000,'unixepoch','localtime'), action, actor, member_name, balance_before, balance_after, balance_delta FROM member_audit_log ORDER BY id DESC LIMIT 20;"
```

## API used by the webpage
- `GET /api/members?search=<name_or_student_number>`
- `POST /api/purchase` body: `{ "id": 1 }`
- `POST /api/admin/login` header: `X-Admin-Password: ****`
- `POST /api/admin/add` header: `X-Admin-Password: ****`
- `POST /api/admin/remove` header: `X-Admin-Password: ****`
- `POST /api/admin/edit-member` header: `X-Admin-Password: ****`
  - body: `{ "id": 1, "name": "Alice", "studentNumber": "12345678", "balanceDelta": 2.0 }`
- `GET /api/admin/export-csv` header: `X-Admin-Password: ****`
- `POST /api/admin/import-csv` header: `X-Admin-Password: ****`
  - body: `{ "csv": "Name,StudentNumber,Balance\\nAlice,12345678,5.00\\n" }`
- `POST /api/admin/set-drink-price` header: `X-Admin-Password: ****`
  - body: `{ "drinkPrice": 1.50 }`
