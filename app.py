from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("ADDRESS_BOOK_DB", BASE_DIR / "address_book.db"))

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_db()) as db, db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def serialize_contact(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "email": row["email"],
        "company": row["company"],
        "notes": row["notes"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def validate_contact(body: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    contact = {
        "name": str(body.get("name", "")).strip()[:100],
        "phone": str(body.get("phone", "")).strip()[:50],
        "email": str(body.get("email", "")).strip()[:120],
        "company": str(body.get("company", "")).strip()[:120],
        "notes": str(body.get("notes", "")).strip()[:1000],
    }
    if not contact["name"]:
        return None, "联系人姓名不能为空"
    if not contact["phone"] and not contact["email"]:
        return None, "电话和邮箱至少填写一项"
    if contact["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact["email"]):
        return None, "邮箱格式不正确"
    return contact, None


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/contacts")
def list_contacts():
    query = request.args.get("q", "").strip()
    sql = "SELECT * FROM contacts"
    params: list[str] = []
    if query:
        sql += " WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? OR company LIKE ?"
        pattern = f"%{query}%"
        params = [pattern, pattern, pattern, pattern]
    sql += " ORDER BY name COLLATE NOCASE, id DESC"

    with closing(get_db()) as db:
        contacts = [serialize_contact(row) for row in db.execute(sql, params).fetchall()]
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    return jsonify({"contacts": contacts, "total": total})


@app.post("/api/contacts")
def create_contact():
    contact, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert contact is not None

    with closing(get_db()) as db, db:
        cursor = db.execute(
            "INSERT INTO contacts (name, phone, email, company, notes) VALUES (?, ?, ?, ?, ?)",
            tuple(contact.values()),
        )
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(serialize_contact(row)), 201


@app.put("/api/contacts/<int:contact_id>")
def update_contact(contact_id: int):
    contact, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert contact is not None

    with closing(get_db()) as db, db:
        cursor = db.execute(
            """
            UPDATE contacts
            SET name = ?, phone = ?, email = ?, company = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*contact.values(), contact_id),
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "联系人不存在"}), 404
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return jsonify(serialize_contact(row))


@app.delete("/api/contacts/<int:contact_id>")
def delete_contact(contact_id: int):
    with closing(get_db()) as db, db:
        cursor = db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "联系人不存在"}), 404
    return "", 204


init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
