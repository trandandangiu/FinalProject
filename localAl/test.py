import unittest
import requests
import json

BASE_URL = "http://localhost:5000/api"

EMAIL = "attran2003@tis.edu.vn"
PASSWORD = "Khanhan091005@"

class TestChatServiceReal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Đăng nhập để lấy JWT
        login_url = f"{BASE_URL}/login"
        resp = requests.post(login_url, json={"email": EMAIL, "password": PASSWORD})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        cls.token = data["access_token"]
        print("\n✅ Login thành công, token:", cls.token[:40] + "...")

    def call_chat(self, message):
        url = f"{BASE_URL}/chat"
        resp = requests.post(
            url,
            json={"message": message},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        print(f"\n[TEST] {message}\nStatus: {resp.status_code}\nResponse: {resp.text}")
        return resp

    def test_progress_check(self):
        resp = self.call_chat("tiến độ của tôi")
        self.assertEqual(resp.status_code, 200)

    def test_food_lookup(self):
        resp = self.call_chat("100g gạo trắng có bao nhiêu calo")
        self.assertEqual(resp.status_code, 200)

    def test_workout_suggestion(self):
        resp = self.call_chat("bài tập cho cơ bụng")
        self.assertEqual(resp.status_code, 200)

    def test_meal_suggestion(self):
        resp = self.call_chat("hôm nay nên ăn gì để tăng cơ")
        self.assertEqual(resp.status_code, 200)

    def test_recommendation(self):
        resp = self.call_chat("gợi ý kế hoạch tuần")
        self.assertEqual(resp.status_code, 200)

    def test_fallback(self):
        resp = self.call_chat("xin chào")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
