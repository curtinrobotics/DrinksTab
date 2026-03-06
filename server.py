#!/usr/bin/env python3
"""CRoC Drinks Tab backend.

Serves the single-page app and provides a local SQLite-backed API.
"""

import csv
import io
import json
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "drinks_tab.db"
HOST = "127.0.0.1"
PORT = 8000
ADMIN_PASSWORD = "CR0C"
DEFAULT_DRINK_PRICE = 1.0


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_ms() -> int:
    return int(time.time() * 1000)


def normalized_student_number(student_number: str) -> str | None:
    value = (student_number or "").strip()
    return value if value else None


def init_db() -> None:
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                student_number TEXT,
                balance REAL NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS member_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time_ms INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                member_id INTEGER,
                member_name TEXT,
                student_number TEXT,
                balance_before REAL,
                balance_after REAL,
                balance_delta REAL,
                details TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        # Migration guard for older schema versions.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(members)").fetchall()}
        if "student_number" not in columns:
            conn.execute("ALTER TABLE members ADD COLUMN student_number TEXT")

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_members_student_number
            ON members(student_number)
            WHERE student_number IS NOT NULL AND TRIM(student_number) <> ''
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value)
            VALUES ('drink_price', ?)
            """,
            (str(DEFAULT_DRINK_PRICE),),
        )
        conn.commit()


def log_member_change(
    conn: sqlite3.Connection,
    *,
    action: str,
    actor: str,
    member_id: int | None = None,
    member_name: str | None = None,
    student_number: str | None = None,
    balance_before: float | None = None,
    balance_after: float | None = None,
    balance_delta: float | None = None,
    details: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO member_audit_log (
            event_time_ms, action, actor, member_id, member_name, student_number,
            balance_before, balance_after, balance_delta, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_ms(),
            action,
            actor,
            member_id,
            member_name,
            student_number,
            balance_before,
            balance_after,
            balance_delta,
            details,
        ),
    )


def serialize_member(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "studentNumber": row["student_number"] or "",
        "balance": float(row["balance"]),
    }


def get_drink_price(conn: sqlite3.Connection | None = None) -> float:
    if conn is None:
        with db_conn() as new_conn:
            return get_drink_price(new_conn)

    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'drink_price' LIMIT 1"
    ).fetchone()
    if row is None:
        return DEFAULT_DRINK_PRICE
    try:
        value = float(row["value"])
        if value <= 0:
            return DEFAULT_DRINK_PRICE
        return value
    except (TypeError, ValueError):
        return DEFAULT_DRINK_PRICE


def set_drink_price(new_price: float) -> None:
    if new_price <= 0:
        raise ValueError("drink price must be greater than 0")

    with db_conn() as conn:
        old_price = get_drink_price(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (key, value)
            VALUES ('drink_price', ?)
            """,
            (str(round(new_price, 2)),),
        )
        log_member_change(
            conn,
            action="set_drink_price",
            actor="admin",
            balance_before=round(old_price, 2),
            balance_after=round(new_price, 2),
            balance_delta=round(new_price - old_price, 2),
            details="Updated drink price setting",
        )
        conn.commit()


def get_member_by_id(conn: sqlite3.Connection, member_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, student_number, balance FROM members WHERE id = ? LIMIT 1",
        (member_id,),
    ).fetchone()


def get_member_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, student_number, balance FROM members WHERE name = ? COLLATE NOCASE LIMIT 1",
        (name,),
    ).fetchone()


def list_members(search: str | None = None) -> list[dict]:
    query = "SELECT id, name, student_number, balance FROM members"
    params: list[str] = []

    if search:
        query += " WHERE name LIKE ? COLLATE NOCASE OR student_number LIKE ? COLLATE NOCASE"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY name COLLATE NOCASE ASC"

    with db_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    return [serialize_member(row) for row in rows]


def add_member(name: str, student_number: str, balance: float) -> None:
    if not name:
        raise ValueError("name is required")
    if balance < 0:
        raise ValueError("balance cannot be negative")

    clean_student = normalized_student_number(student_number)
    clean_balance = round(balance, 2)

    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO members (name, student_number, balance) VALUES (?, ?, ?)",
            (name, clean_student, clean_balance),
        )

        log_member_change(
            conn,
            action="add_member",
            actor="admin",
            member_id=int(cur.lastrowid),
            member_name=name,
            student_number=clean_student,
            balance_before=0.0,
            balance_after=clean_balance,
            balance_delta=clean_balance,
            details="Member created",
        )
        conn.commit()


def remove_member(name: str) -> None:
    if not name:
        raise ValueError("name is required")

    with db_conn() as conn:
        row = get_member_by_name(conn, name)
        if row is None:
            raise ValueError("member not found")

        conn.execute("DELETE FROM members WHERE id = ?", (int(row["id"]),))
        existing_balance = float(row["balance"])

        log_member_change(
            conn,
            action="remove_member",
            actor="admin",
            member_id=int(row["id"]),
            member_name=row["name"],
            student_number=row["student_number"] or "",
            balance_before=existing_balance,
            balance_after=0.0,
            balance_delta=round(-existing_balance, 2),
            details="Member removed",
        )
        conn.commit()


def set_balance(name: str, balance: float) -> None:
    if not name:
        raise ValueError("name is required")
    if balance < 0:
        raise ValueError("balance cannot be negative")

    with db_conn() as conn:
        row = get_member_by_name(conn, name)
        if row is None:
            raise ValueError("member not found")

        before_balance = float(row["balance"])
        after_balance = round(balance, 2)
        conn.execute("UPDATE members SET balance = ? WHERE id = ?", (after_balance, int(row["id"])))

        log_member_change(
            conn,
            action="set_balance",
            actor="admin",
            member_id=int(row["id"]),
            member_name=row["name"],
            student_number=row["student_number"] or "",
            balance_before=before_balance,
            balance_after=after_balance,
            balance_delta=round(after_balance - before_balance, 2),
            details="Balance set directly",
        )
        conn.commit()


def adjust_balance(name: str, delta: float) -> None:
    if not name:
        raise ValueError("name is required")

    with db_conn() as conn:
        row = get_member_by_name(conn, name)
        if row is None:
            raise ValueError("member not found")

        before_balance = float(row["balance"])
        after_balance = round(before_balance + delta, 2)
        if after_balance < 0:
            raise ValueError("resulting balance cannot be negative")

        conn.execute("UPDATE members SET balance = ? WHERE id = ?", (after_balance, int(row["id"])))
        log_member_change(
            conn,
            action="adjust_balance",
            actor="admin",
            member_id=int(row["id"]),
            member_name=row["name"],
            student_number=row["student_number"] or "",
            balance_before=before_balance,
            balance_after=after_balance,
            balance_delta=round(delta, 2),
            details="Balance adjusted",
        )
        conn.commit()


def purchase_drink_by_id(member_id: int) -> dict:
    with db_conn() as conn:
        row = get_member_by_id(conn, member_id)
        if row is None:
            raise ValueError("member not found")

        before_balance = float(row["balance"])
        drink_price = get_drink_price(conn)
        if before_balance < drink_price:
            raise ValueError("insufficient balance")

        after_balance = round(before_balance - drink_price, 2)
        conn.execute("UPDATE members SET balance = ? WHERE id = ?", (after_balance, int(row["id"])))

        log_member_change(
            conn,
            action="purchase_drink",
            actor="member",
            member_id=int(row["id"]),
            member_name=row["name"],
            student_number=row["student_number"] or "",
            balance_before=before_balance,
            balance_after=after_balance,
            balance_delta=round(-drink_price, 2),
            details=f"Drink purchased at ${drink_price:.2f}",
        )
        conn.commit()

    member = serialize_member(row)
    member["balance"] = after_balance
    return member


def purchase_drink(name: str) -> dict:
    if not name:
        raise ValueError("name is required")

    with db_conn() as conn:
        row = get_member_by_name(conn, name)
        if row is None:
            raise ValueError("member not found")
    return purchase_drink_by_id(int(row["id"]))


def edit_member(member_id: int, name: str, student_number: str, balance_delta: float) -> None:
    if not name:
        raise ValueError("name is required")

    clean_student = normalized_student_number(student_number)

    with db_conn() as conn:
        row = get_member_by_id(conn, member_id)
        if row is None:
            raise ValueError("member not found")

        before_balance = float(row["balance"])
        after_balance = round(before_balance + balance_delta, 2)
        if after_balance < 0:
            raise ValueError("resulting balance cannot be negative")

        conn.execute(
            """
            UPDATE members
            SET name = ?, student_number = ?, balance = ?
            WHERE id = ?
            """,
            (name, clean_student, after_balance, member_id),
        )

        log_member_change(
            conn,
            action="edit_member",
            actor="admin",
            member_id=int(row["id"]),
            member_name=name,
            student_number=clean_student or "",
            balance_before=before_balance,
            balance_after=after_balance,
            balance_delta=round(balance_delta, 2),
            details=f"Name/student number edited from {row['name']}/{row['student_number'] or ''}",
        )
        conn.commit()


def import_members_from_csv(csv_text: str) -> None:
    if not csv_text or not csv_text.strip():
        raise ValueError("csv content is empty")

    reader = csv.DictReader(io.StringIO(csv_text))
    required = ["Name", "StudentNumber", "Balance"]
    if not reader.fieldnames or list(reader.fieldnames) != required:
        raise ValueError("csv must have header: Name,StudentNumber,Balance")

    rows_to_insert: list[tuple[str, str | None, float]] = []
    seen_names: set[str] = set()
    seen_students: set[str] = set()

    for line_no, row in enumerate(reader, start=2):
        name = str(row.get("Name", "")).strip()
        student = normalized_student_number(str(row.get("StudentNumber", "")).strip())
        balance_text = str(row.get("Balance", "")).strip()

        if not name:
            raise ValueError(f"row {line_no}: name is required")

        name_key = name.casefold()
        if name_key in seen_names:
            raise ValueError(f"row {line_no}: duplicate name in csv ({name})")
        seen_names.add(name_key)

        if student:
            student_key = student.casefold()
            if student_key in seen_students:
                raise ValueError(f"row {line_no}: duplicate student number in csv ({student})")
            seen_students.add(student_key)

        try:
            balance = round(float(balance_text), 2)
        except (TypeError, ValueError):
            raise ValueError(f"row {line_no}: invalid balance")

        if balance < 0:
            raise ValueError(f"row {line_no}: balance cannot be negative")

        rows_to_insert.append((name, student, balance))

    with db_conn() as conn:
        old_count = int(conn.execute("SELECT COUNT(*) AS count FROM members").fetchone()["count"])
        conn.execute("DELETE FROM members")

        for name, student, balance in rows_to_insert:
            cur = conn.execute(
                "INSERT INTO members (name, student_number, balance) VALUES (?, ?, ?)",
                (name, student, balance),
            )
            log_member_change(
                conn,
                action="import_csv_initialize_member",
                actor="admin",
                member_id=int(cur.lastrowid),
                member_name=name,
                student_number=student or "",
                balance_before=0.0,
                balance_after=balance,
                balance_delta=balance,
                details="Inserted from CSV initialize import",
            )

        log_member_change(
            conn,
            action="import_csv_initialize",
            actor="admin",
            details=f"Replaced members table from CSV (old_count={old_count}, new_count={len(rows_to_insert)})",
        )
        conn.commit()


def export_members_csv() -> str:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT name, student_number, balance FROM members ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "StudentNumber", "Balance"])
    for row in rows:
        writer.writerow([row["name"], row["student_number"] or "", f"{float(row['balance']):.2f}"])
    return output.getvalue()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self, filename: str, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def is_admin(self) -> bool:
        return self.headers.get("X-Admin-Password", "") == ADMIN_PASSWORD

    def require_admin(self) -> bool:
        if self.is_admin():
            return True
        self.send_json(401, {"error": "admin password required"})
        return False

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/members":
            qs = parse_qs(parsed.query)
            search = (qs.get("search", [""])[0] or "").strip()
            self.send_json(
                200,
                {
                    "members": list_members(search),
                    "drinkPrice": get_drink_price(),
                },
            )
            return

        if parsed.path == "/api/admin/export-csv":
            if not self.require_admin():
                return
            self.send_csv("drinks_members_export.csv", export_members_csv())
            return

        if parsed.path == "/":
            self.path = "/croc_drinks_tab.html"
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/purchase":
                payload = self.read_json()
                member_id = payload.get("id")
                if member_id is not None:
                    member = purchase_drink_by_id(int(member_id))
                else:
                    member = purchase_drink(str(payload.get("name", "")).strip())
                self.send_json(200, {"ok": True, "member": member})
                return

            if parsed.path == "/api/admin/login":
                if not self.is_admin():
                    self.send_json(401, {"error": "invalid admin password"})
                    return
                self.send_json(200, {"ok": True})
                return

            if parsed.path in {
                "/api/admin/add",
                "/api/admin/remove",
                "/api/admin/set-balance",
                "/api/admin/adjust-balance",
                "/api/admin/edit-member",
                "/api/admin/import-csv",
                "/api/admin/set-drink-price",
            }:
                if not self.require_admin():
                    return

                payload = self.read_json()
                name = str(payload.get("name", "")).strip()

                if parsed.path == "/api/admin/add":
                    add_member(name, str(payload.get("studentNumber", "")).strip(), float(payload.get("balance", 0)))
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/remove":
                    remove_member(name)
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/set-balance":
                    set_balance(name, float(payload.get("balance", 0)))
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/adjust-balance":
                    adjust_balance(name, float(payload.get("delta", 0)))
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/edit-member":
                    edit_member(
                        int(payload.get("id", 0)),
                        name,
                        str(payload.get("studentNumber", "")).strip(),
                        float(payload.get("balanceDelta", 0)),
                    )
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/import-csv":
                    import_members_from_csv(str(payload.get("csv", "")))
                    self.send_json(200, {"ok": True})
                    return

                if parsed.path == "/api/admin/set-drink-price":
                    set_drink_price(float(payload.get("drinkPrice", 0)))
                    self.send_json(200, {"ok": True})
                    return

            self.send_json(404, {"error": "not found"})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid JSON body"})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except sqlite3.IntegrityError:
            self.send_json(400, {"error": "member name or student number already exists"})
        except sqlite3.Error as exc:
            self.send_json(500, {"error": f"database error: {exc}"})


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Running on http://{HOST}:{PORT}")
    print(f"Database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
