from __future__ import annotations

import io
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file, session
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("ADDRESS_BOOK_DB", BASE_DIR / "address_book.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("ADDRESS_BOOK_SECRET", "local-development-only-change-before-deployment")
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

METHOD_TYPES = {"phone", "email", "social", "address", "other"}
METHOD_LABELS = {
    "phone": "电话",
    "email": "邮箱",
    "social": "社交账号",
    "address": "地址",
    "other": "其他",
}


def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_db()) as db, db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contact_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                value TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(contacts)").fetchall()}
        if "user_id" not in columns:
            db.execute("ALTER TABLE contacts ADD COLUMN user_id INTEGER")
        db.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id)")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_codes_phone_purpose ON verification_codes(phone, purpose, consumed)"
        )


def serialize_contact(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    methods = db.execute(
        "SELECT id, type, label, value FROM contact_methods WHERE contact_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "name": row["name"],
        "company": row["company"],
        "notes": row["notes"],
        "isFavorite": bool(row["is_favorite"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "methods": [dict(method) for method in methods],
    }


def validate_contact(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    name = str(payload.get("name", "")).strip()
    if not name:
        return None, "联系人姓名不能为空"
    if len(name) > 80:
        return None, "联系人姓名不能超过80个字符"

    methods: list[dict[str, str]] = []
    for raw_method in payload.get("methods", []):
        method_type = str(raw_method.get("type", "other")).strip().lower()
        value = str(raw_method.get("value", "")).strip()
        label = str(raw_method.get("label", "")).strip()
        if not value:
            continue
        if method_type not in METHOD_TYPES:
            return None, f"不支持的联系方式类型：{method_type}"
        methods.append({"type": method_type, "label": label[:30], "value": value[:240]})

    return {
        "name": name,
        "company": str(payload.get("company", "")).strip()[:100],
        "notes": str(payload.get("notes", "")).strip()[:1000],
        "is_favorite": 1 if payload.get("isFavorite", False) else 0,
        "methods": methods,
    }, None


def save_methods(db: sqlite3.Connection, contact_id: int, methods: list[dict[str, str]]) -> None:
    db.execute("DELETE FROM contact_methods WHERE contact_id = ?", (contact_id,))
    db.executemany(
        "INSERT INTO contact_methods (contact_id, type, label, value) VALUES (?, ?, ?, ?)",
        [(contact_id, item["type"], item["label"], item["value"]) for item in methods],
    )


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.replace("；", ";").split(";") if item.strip()]


def valid_phone(phone: str) -> bool:
    return bool(re.fullmatch(r"1[3-9]\d{9}", phone))


def current_user_id() -> int | None:
    value = session.get("user_id")
    return int(value) if value is not None else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user_id() is None:
            return jsonify({"error": "请先登录", "authRequired": True}), 401
        return view(*args, **kwargs)

    return wrapped


def verify_code(db: sqlite3.Connection, phone: str, purpose: str, code: str) -> bool:
    row = db.execute(
        """
        SELECT * FROM verification_codes
        WHERE phone = ? AND purpose = ? AND consumed = 0
        ORDER BY id DESC LIMIT 1
        """,
        (phone, purpose),
    ).fetchone()
    if not row or row["expires_at"] < int(time.time()):
        return False
    if not check_password_hash(row["code_hash"], code):
        return False
    db.execute("UPDATE verification_codes SET consumed = 1 WHERE id = ?", (row["id"],))
    return True


@app.errorhandler(413)
def file_too_large(_: Exception):
    return jsonify({"error": "文件不能超过5MB"}), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/auth/status")
def auth_status():
    user_id = current_user_id()
    with closing(get_db()) as db:
        user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        user = None
        if user_id is not None:
            row = db.execute("SELECT id, username, phone FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                user = dict(row)
            else:
                session.clear()
    return jsonify({"loggedIn": user is not None, "hasAccounts": user_count > 0, "user": user})


@app.post("/api/auth/send-code")
def send_verification_code():
    body = request.get_json(silent=True) or {}
    phone = str(body.get("phone", "")).strip()
    purpose = str(body.get("purpose", "")).strip()
    if not valid_phone(phone):
        return jsonify({"error": "请输入有效的11位中国大陆手机号"}), 400
    if purpose not in {"register", "reset"}:
        return jsonify({"error": "验证码用途无效"}), 400

    with closing(get_db()) as db, db:
        exists = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if purpose == "register" and exists:
            return jsonify({"error": "该手机号已经注册"}), 409
        if purpose == "reset" and not exists:
            return jsonify({"error": "该手机号尚未注册"}), 404
        recent = db.execute(
            """
            SELECT expires_at FROM verification_codes
            WHERE phone = ? AND purpose = ? AND consumed = 0
            ORDER BY id DESC LIMIT 1
            """,
            (phone, purpose),
        ).fetchone()
        now = int(time.time())
        if recent and recent["expires_at"] - 540 > now:
            return jsonify({"error": "验证码发送过于频繁，请稍后再试"}), 429
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.execute(
            "INSERT INTO verification_codes (phone, purpose, code_hash, expires_at) VALUES (?, ?, ?, ?)",
            (phone, purpose, generate_password_hash(code), now + 600),
        )

    app.logger.info("Local demo verification code for %s (%s): %s", phone, purpose, code)
    return jsonify(
        {
            "message": "本地验证码已生成，10分钟内有效",
            "demoCode": code,
            "demoMode": True,
            "expiresIn": 600,
        }
    )


@app.post("/api/auth/register")
def register():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    phone = str(body.get("phone", "")).strip()
    password = str(body.get("password", ""))
    code = str(body.get("code", "")).strip()
    if not 2 <= len(username) <= 30:
        return jsonify({"error": "用户名长度应为2至30个字符"}), 400
    if not valid_phone(phone):
        return jsonify({"error": "请输入有效的11位中国大陆手机号"}), 400
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return jsonify({"error": "密码至少8位，并同时包含字母和数字"}), 400

    with closing(get_db()) as db, db:
        if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            return jsonify({"error": "该用户名已被使用"}), 409
        if db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone():
            return jsonify({"error": "该手机号已经注册"}), 409
        if not verify_code(db, phone, "register", code):
            return jsonify({"error": "验证码错误或已过期"}), 400
        cursor = db.execute(
            "INSERT INTO users (username, phone, password_hash) VALUES (?, ?, ?)",
            (username, phone, generate_password_hash(password)),
        )
        user_id = int(cursor.lastrowid)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
            db.execute("UPDATE contacts SET user_id = ? WHERE user_id IS NULL", (user_id,))
    session.clear()
    session["user_id"] = user_id
    return jsonify({"message": "注册成功", "user": {"id": user_id, "username": username, "phone": phone}}), 201


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    account = str(body.get("account", "")).strip()
    password = str(body.get("password", ""))
    with closing(get_db()) as db:
        user = db.execute(
            "SELECT * FROM users WHERE username = ? OR phone = ?", (account, account)
        ).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "账号或密码错误"}), 401
    session.clear()
    session["user_id"] = int(user["id"])
    return jsonify(
        {"message": "登录成功", "user": {"id": user["id"], "username": user["username"], "phone": user["phone"]}}
    )


@app.post("/api/auth/reset-password")
def reset_password():
    body = request.get_json(silent=True) or {}
    phone = str(body.get("phone", "")).strip()
    password = str(body.get("password", ""))
    code = str(body.get("code", "")).strip()
    if not valid_phone(phone):
        return jsonify({"error": "请输入有效的11位中国大陆手机号"}), 400
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return jsonify({"error": "密码至少8位，并同时包含字母和数字"}), 400
    with closing(get_db()) as db, db:
        user = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if not user:
            return jsonify({"error": "该手机号尚未注册"}), 404
        if not verify_code(db, phone, "reset", code):
            return jsonify({"error": "验证码错误或已过期"}), 400
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
    return jsonify({"message": "密码已重置，请使用新密码登录"})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "已安全退出"})


@app.get("/api/contacts")
@login_required
def list_contacts():
    user_id = current_user_id()
    query = request.args.get("q", "").strip()
    favorites_only = request.args.get("favorite") == "1"
    sql = """
        SELECT DISTINCT c.* FROM contacts c
        LEFT JOIN contact_methods m ON m.contact_id = c.id
        WHERE c.user_id = ?
    """
    params: list[Any] = [user_id]
    if favorites_only:
        sql += " AND c.is_favorite = 1"
    if query:
        pattern = f"%{query}%"
        sql += " AND (c.name LIKE ? OR c.company LIKE ? OR m.value LIKE ?)"
        params.extend([pattern, pattern, pattern])
    sql += " ORDER BY c.is_favorite DESC, c.name COLLATE NOCASE, c.id DESC"

    with closing(get_db()) as db, db:
        rows = db.execute(sql, params).fetchall()
        contacts = [serialize_contact(db, row) for row in rows]
        total = db.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ?", (user_id,)).fetchone()[0]
        favorite_count = db.execute(
            "SELECT COUNT(*) FROM contacts WHERE user_id = ? AND is_favorite = 1", (user_id,)
        ).fetchone()[0]
    return jsonify({"contacts": contacts, "total": total, "favoriteCount": favorite_count})


@app.post("/api/contacts")
@login_required
def create_contact():
    user_id = current_user_id()
    payload, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert payload is not None
    with closing(get_db()) as db, db:
        cursor = db.execute(
            "INSERT INTO contacts (name, company, notes, is_favorite, user_id) VALUES (?, ?, ?, ?, ?)",
            (payload["name"], payload["company"], payload["notes"], payload["is_favorite"], user_id),
        )
        contact_id = cursor.lastrowid
        assert contact_id is not None
        save_methods(db, contact_id, payload["methods"])
        row = db.execute("SELECT * FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)).fetchone()
        contact = serialize_contact(db, row)
    return jsonify(contact), 201


@app.put("/api/contacts/<int:contact_id>")
@login_required
def update_contact(contact_id: int):
    user_id = current_user_id()
    payload, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert payload is not None
    with closing(get_db()) as db, db:
        exists = db.execute(
            "SELECT id FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)
        ).fetchone()
        if not exists:
            return jsonify({"error": "联系人不存在"}), 404
        db.execute(
            """
            UPDATE contacts
            SET name = ?, company = ?, notes = ?, is_favorite = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (
                payload["name"],
                payload["company"],
                payload["notes"],
                payload["is_favorite"],
                contact_id,
                user_id,
            ),
        )
        save_methods(db, contact_id, payload["methods"])
        row = db.execute("SELECT * FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)).fetchone()
        contact = serialize_contact(db, row)
    return jsonify(contact)


@app.patch("/api/contacts/<int:contact_id>/favorite")
@login_required
def toggle_favorite(contact_id: int):
    user_id = current_user_id()
    body = request.get_json(silent=True) or {}
    with closing(get_db()) as db, db:
        row = db.execute(
            "SELECT * FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "联系人不存在"}), 404
        desired = body.get("isFavorite")
        favorite = int(bool(desired)) if desired is not None else int(not bool(row["is_favorite"]))
        db.execute(
            "UPDATE contacts SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (favorite, contact_id, user_id),
        )
        updated = db.execute(
            "SELECT * FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)
        ).fetchone()
        contact = serialize_contact(db, updated)
    return jsonify(contact)


@app.delete("/api/contacts/<int:contact_id>")
@login_required
def delete_contact(contact_id: int):
    user_id = current_user_id()
    with closing(get_db()) as db, db:
        cursor = db.execute("DELETE FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id))
        if cursor.rowcount == 0:
            return jsonify({"error": "联系人不存在"}), 404
    return "", 204


@app.get("/api/export")
@login_required
def export_contacts():
    user_id = current_user_id()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "通讯录"
    headers = ["姓名", "公司/组织", "收藏", "电话号码", "电子邮箱", "社交账号", "地址", "其他", "备注"]
    sheet.append(headers)

    with closing(get_db()) as db, db:
        rows = db.execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY is_favorite DESC, name", (user_id,)
        ).fetchall()
        for row in rows:
            contact = serialize_contact(db, row)
            grouped = {key: [] for key in METHOD_TYPES}
            for method in contact["methods"]:
                label_prefix = f'{method["label"]}：' if method["label"] else ""
                grouped[method["type"]].append(f'{label_prefix}{method["value"]}')
            sheet.append(
                [
                    contact["name"],
                    contact["company"],
                    "是" if contact["isFavorite"] else "否",
                    "; ".join(grouped["phone"]),
                    "; ".join(grouped["email"]),
                    "; ".join(grouped["social"]),
                    "; ".join(grouped["address"]),
                    "; ".join(grouped["other"]),
                    contact["notes"],
                ]
            )

    header_fill = PatternFill("solid", fgColor="215B55")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = [18, 22, 10, 30, 32, 30, 36, 30, 40]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="address-book.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/import")
@login_required
def import_contacts():
    user_id = current_user_id()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "请选择Excel文件"}), 400
    if not upload.filename.lower().endswith(".xlsx"):
        return jsonify({"error": "仅支持.xlsx格式的Excel文件"}), 400

    try:
        workbook = load_workbook(upload, read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        raw_headers = next(rows, None)
        if not raw_headers:
            return jsonify({"error": "Excel文件为空"}), 400
        headers = {str(value).strip(): index for index, value in enumerate(raw_headers) if value is not None}
        if "姓名" not in headers:
            return jsonify({"error": "Excel缺少“姓名”列，请先导出模板后填写"}), 400

        imported = 0
        skipped = 0
        with closing(get_db()) as db, db:
            for values in rows:
                def cell(title: str) -> Any:
                    index = headers.get(title)
                    return values[index] if index is not None and index < len(values) else ""

                name = str(cell("姓名") or "").strip()
                if not name:
                    skipped += 1
                    continue
                favorite = str(cell("收藏") or "").strip().lower() in {"是", "yes", "true", "1", "y"}
                cursor = db.execute(
                    "INSERT INTO contacts (name, company, notes, is_favorite, user_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        name[:80],
                        str(cell("公司/组织") or "")[:100],
                        str(cell("备注") or "")[:1000],
                        int(favorite),
                        user_id,
                    ),
                )
                contact_id = cursor.lastrowid
                column_types = {
                    "电话号码": "phone",
                    "电子邮箱": "email",
                    "社交账号": "social",
                    "地址": "address",
                    "其他": "other",
                }
                methods = []
                for column, method_type in column_types.items():
                    for item in split_values(cell(column)):
                        label, separator, value = item.partition("：")
                        if not separator:
                            label, separator, value = item.partition(":")
                        methods.append(
                            {
                                "type": method_type,
                                "label": label.strip()[:30] if separator else "",
                                "value": value.strip()[:240] if separator else item[:240],
                            }
                        )
                save_methods(db, int(contact_id), methods)
                imported += 1
        return jsonify({"message": f"成功导入{imported}位联系人", "imported": imported, "skipped": skipped})
    except Exception as exc:
        app.logger.exception("Excel import failed")
        return jsonify({"error": f"无法读取Excel文件：{exc}"}), 400


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
else:
    init_db()
