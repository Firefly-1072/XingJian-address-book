import io
import os
import tempfile
import unittest

from openpyxl import load_workbook


class AddressBookTestCase(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.database_file.close()
        os.environ["ADDRESS_BOOK_DB"] = self.database_file.name

        import app as address_app

        address_app.DATABASE = address_app.Path(self.database_file.name)
        address_app.init_db()
        address_app.app.config.update(TESTING=True)
        self.client = address_app.app.test_client()

    def tearDown(self):
        os.unlink(self.database_file.name)

    def create_contact(self, name="林晓然", favorite=True):
        return self.client.post(
            "/api/contacts",
            json={
                "name": name,
                "company": "福州大学",
                "notes": "课程项目伙伴",
                "isFavorite": favorite,
                "methods": [
                    {"type": "phone", "label": "手机", "value": "13800000000"},
                    {"type": "email", "label": "学校", "value": "student@example.com"},
                ],
            },
        )

    def test_create_list_and_favorite_filter(self):
        response = self.create_contact()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.get_json()["methods"]), 2)

        data = self.client.get("/api/contacts?favorite=1").get_json()
        self.assertEqual(data["favoriteCount"], 1)
        self.assertEqual(data["contacts"][0]["name"], "林晓然")

    def test_update_toggle_and_delete_contact(self):
        contact = self.create_contact(favorite=False).get_json()
        contact["name"] = "林晓然（已更新）"
        updated = self.client.put(f'/api/contacts/{contact["id"]}', json=contact)
        self.assertEqual(updated.get_json()["name"], "林晓然（已更新）")

        toggled = self.client.patch(f'/api/contacts/{contact["id"]}/favorite', json={"isFavorite": True})
        self.assertTrue(toggled.get_json()["isFavorite"])
        self.assertEqual(self.client.delete(f'/api/contacts/{contact["id"]}').status_code, 204)

    def test_export_and_import_excel(self):
        self.create_contact()
        exported = self.client.get("/api/export")
        self.assertEqual(exported.status_code, 200)
        workbook = load_workbook(io.BytesIO(exported.data))
        self.assertEqual(workbook.active["A1"].value, "姓名")
        self.assertEqual(workbook.active["A2"].value, "林晓然")

        imported = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(exported.data), "contacts.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.get_json()["imported"], 1)

    def test_validation(self):
        self.assertEqual(self.client.post("/api/contacts", json={"name": ""}).status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/contacts",
                json={"name": "无效类型", "methods": [{"type": "fax", "value": "123"}]},
            ).status_code,
            400,
        )

if __name__ == "__main__":
    unittest.main()
