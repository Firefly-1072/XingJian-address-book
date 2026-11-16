import os
import tempfile
import unittest


class BasicAddressBookTestCase(unittest.TestCase):
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

    def create_contact(self, name="林晓然"):
        return self.client.post(
            "/api/contacts",
            json={
                "name": name,
                "phone": "13800000000",
                "email": "student@example.com",
                "company": "福州大学",
                "notes": "课程项目伙伴",
            },
        )

    def test_home_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("星笺".encode("utf-8"), response.data)

    def test_create_list_update_and_delete(self):
        created = self.create_contact()
        self.assertEqual(created.status_code, 201)
        contact = created.get_json()

        listing = self.client.get("/api/contacts").get_json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["contacts"][0]["name"], "林晓然")

        contact["name"] = "林晓然（已更新）"
        updated = self.client.put(f'/api/contacts/{contact["id"]}', json=contact)
        self.assertEqual(updated.get_json()["name"], "林晓然（已更新）")

        deleted = self.client.delete(f'/api/contacts/{contact["id"]}')
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/contacts").get_json()["total"], 0)

    def test_search(self):
        self.create_contact("星笺测试联系人")
        result = self.client.get("/api/contacts?q=星笺").get_json()
        self.assertEqual(len(result["contacts"]), 1)

    def test_validation(self):
        missing_name = self.client.post("/api/contacts", json={"phone": "13800000000"})
        self.assertEqual(missing_name.status_code, 400)
        missing_method = self.client.post("/api/contacts", json={"name": "测试"})
        self.assertEqual(missing_method.status_code, 400)
        invalid_email = self.client.post(
            "/api/contacts", json={"name": "测试", "email": "invalid"}
        )
        self.assertEqual(invalid_email.status_code, 400)


if __name__ == "__main__":
    unittest.main()
