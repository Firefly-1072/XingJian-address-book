from __future__ import annotations

import io
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("ADDRESS_BOOK_DB", BASE_DIR / "address_book.db"))

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

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

            """
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


@app.errorhandler(413)
def file_too_large(_: Exception):
    return jsonify({"error": "文件不能超过5MB"}), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/contacts")
def list_contacts():
    query = request.args.get("q", "").strip()
    favorites_only = request.args.get("favorite") == "1"
    sql = """
        SELECT DISTINCT c.* FROM contacts c
        LEFT JOIN contact_methods m ON m.contact_id = c.id
        WHERE 1 = 1
    """
    params: list[Any] = []
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
        total = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        favorite_count = db.execute(
            "SELECT COUNT(*) FROM contacts WHERE is_favorite = 1"
        ).fetchone()[0]
    return jsonify({"contacts": contacts, "total": total, "favoriteCount": favorite_count})


@app.post("/api/contacts")
def create_contact():
    payload, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert payload is not None
    with closing(get_db()) as db, db:
        cursor = db.execute(
            "INSERT INTO contacts (name, company, notes, is_favorite) VALUES (?, ?, ?, ?)",
            (payload["name"], payload["company"], payload["notes"], payload["is_favorite"]),
        )
        contact_id = cursor.lastrowid
        assert contact_id is not None
        save_methods(db, contact_id, payload["methods"])
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        contact = serialize_contact(db, row)
    return jsonify(contact), 201


@app.put("/api/contacts/<int:contact_id>")
def update_contact(contact_id: int):
    payload, error = validate_contact(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    assert payload is not None
    with closing(get_db()) as db, db:
        exists = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not exists:
            return jsonify({"error": "联系人不存在"}), 404
        db.execute(
            """
            UPDATE contacts
            SET name = ?, company = ?, notes = ?, is_favorite = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                payload["name"],
                payload["company"],
                payload["notes"],
                payload["is_favorite"],
                contact_id,
            ),
        )
        save_methods(db, contact_id, payload["methods"])
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        contact = serialize_contact(db, row)
    return jsonify(contact)


@app.patch("/api/contacts/<int:contact_id>/favorite")
def toggle_favorite(contact_id: int):
    body = request.get_json(silent=True) or {}
    with closing(get_db()) as db, db:
        row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not row:
            return jsonify({"error": "联系人不存在"}), 404
        desired = body.get("isFavorite")
        favorite = int(bool(desired)) if desired is not None else int(not bool(row["is_favorite"]))
        db.execute(
            "UPDATE contacts SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (favorite, contact_id),
        )
        updated = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        contact = serialize_contact(db, updated)
    return jsonify(contact)


@app.delete("/api/contacts/<int:contact_id>")
def delete_contact(contact_id: int):
    with closing(get_db()) as db, db:
        cursor = db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "联系人不存在"}), 404
    return "", 204


@app.get("/api/export")
def export_contacts():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "通讯录"
    headers = ["姓名", "公司/组织", "收藏", "电话号码", "电子邮箱", "社交账号", "地址", "其他", "备注"]
    sheet.append(headers)

    with closing(get_db()) as db, db:
        rows = db.execute("SELECT * FROM contacts ORDER BY is_favorite DESC, name").fetchall()
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
def import_contacts():
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
                    "INSERT INTO contacts (name, company, notes, is_favorite) VALUES (?, ?, ?, ?)",
                    (
                        name[:80],
                        str(cell("公司/组织") or "")[:100],
                        str(cell("备注") or "")[:1000],
                        int(favorite),
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
