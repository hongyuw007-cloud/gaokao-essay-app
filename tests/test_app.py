from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from backend.supabase_service import AuthUser


USER = AuthUser(
    id="11111111-1111-1111-1111-111111111111",
    email="student@example.com",
    metadata={
        "name": "测试同学",
        "class_name": "实验1班",
        "student_id": "20260001",
    },
)
AUTH_HEADERS = {"Authorization": "Bearer test-token"}
RECORD = {
    "id": "22222222-2222-2222-2222-222222222222",
    "user_id": USER.id,
    "topic": "论坚持",
    "title": "行而不辍",
    "essay": "《行而不辍》\n\n测试正文。",
    "word_count": 7,
    "is_favorite": False,
    "created_at": "2026-11-04T10:00:00+00:00",
}


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_home_and_health(self) -> None:
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("高考满分作文智能应用", home.text)

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    @patch("backend.main.get_user", return_value=USER)
    def test_profile(self, _get_user) -> None:
        response = self.client.get("/api/profile", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["student_id"], "20260001")

    @patch("backend.main.update_user", return_value=USER)
    @patch("backend.main.get_user", return_value=USER)
    def test_update_profile(self, _get_user, _update_user) -> None:
        response = self.client.put(
            "/api/profile",
            headers=AUTH_HEADERS,
            json={
                "name": "测试同学",
                "class_name": "实验1班",
                "student_id": "20260001",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["name"], "测试同学")

    def test_login_normalizes_auth_user(self) -> None:
        payload = {
            "authenticated": True,
            "access_token": "access",
            "refresh_token": "refresh",
            "token_type": "bearer",
            "user": USER,
        }
        with patch("backend.main.sign_in", return_value=payload):
            response = self.client.post(
                "/api/auth",
                json={
                    "action": "login",
                    "email": "student@example.com",
                    "password": "secret1",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["class_name"], "实验1班")

    @patch("backend.main.list_essays", return_value=[RECORD])
    @patch("backend.main.get_user", return_value=USER)
    def test_list_essays(self, _get_user, _list_essays) -> None:
        response = self.client.get("/api/essays", headers=AUTH_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["title"], "行而不辍")

    @patch("backend.main.create_essay", return_value=RECORD)
    @patch("backend.main.get_user", return_value=USER)
    def test_generate_and_save(self, _get_user, _create_essay) -> None:
        fake_model = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=RECORD["essay"])
                )
            ]
        )
        with (
            patch.object(main, "API_KEY", "test-key"),
            patch.object(
                main.client.chat.completions,
                "create",
                return_value=fake_model,
            ),
        ):
            response = self.client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
                json={"topic": "论坚持"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertEqual(response.json()["record"]["title"], "行而不辍")

    @patch("backend.main.update_essay")
    @patch("backend.main.get_user", return_value=USER)
    def test_toggle_favorite(self, _get_user, _update_essay) -> None:
        _update_essay.return_value = {**RECORD, "is_favorite": True}
        response = self.client.patch(
            "/api/essays",
            headers=AUTH_HEADERS,
            json={"id": RECORD["id"], "is_favorite": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["record"]["is_favorite"])

    @patch("backend.main.delete_essay", return_value=None)
    @patch("backend.main.get_user", return_value=USER)
    def test_delete_essay(self, _get_user, _delete_essay) -> None:
        response = self.client.delete(
            f"/api/essays?id={RECORD['id']}",
            headers=AUTH_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        _delete_essay.assert_called_once_with(
            "test-token",
            essay_id=RECORD["id"],
            user_id=USER.id,
        )


if __name__ == "__main__":
    unittest.main()
