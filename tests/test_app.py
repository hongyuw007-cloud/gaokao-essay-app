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
    def test_save_existing_essay(self, _get_user, _create_essay) -> None:
        response = self.client.post(
            "/api/essays",
            headers=AUTH_HEADERS,
            json={"topic": "论坚持", "essay": RECORD["essay"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record"]["id"], RECORD["id"])
        _create_essay.assert_called_once_with(
            "test-token",
            user_id=USER.id,
            topic="论坚持",
            title="行而不辍",
            essay=RECORD["essay"],
            word_count=11,
        )

    @patch("backend.main.create_essay", return_value=RECORD)
    @patch("backend.main.get_user", return_value=USER)
    def test_generate_and_save(self, _get_user, _create_essay) -> None:
        initial_model = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "【写作策略】\n"
                            "中心立意：坚持需要明确目标和持续行动\n"
                            "文体选择：议论文\n"
                            "结构方式：层进式论证\n"
                            "写作建议：用具体事例支撑每一层观点\n\n"
                            f"【作文正文】\n{RECORD['essay']}"
                        )
                    )
                )
            ]
        )
        revised_essay = "《行而不辍》\n\n" + "行" * 794
        revised_model = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=revised_essay))]
        )
        with (
            patch.object(main, "API_KEY", "test-key"),
            patch.object(
                main.client.chat.completions,
                "create",
                side_effect=[initial_model, revised_model],
            ) as mock_create,
        ):
            response = self.client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
                json={
                    "topic": "论坚持",
                    "material": "坚持不是重复，而是在目标明确后的持续行动。",
                    "genre": "argumentative",
                    "target_word_count": 800,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertEqual(response.json()["record"]["title"], "行而不辍")
        self.assertEqual(response.json()["word_check"]["target"], 800)
        self.assertEqual(response.json()["word_check"]["actual"], 800)
        self.assertEqual(response.json()["word_check"]["status"], "ok")
        self.assertTrue(response.json()["length_revision"]["attempted"])
        self.assertTrue(response.json()["length_revision"]["applied"])
        self.assertEqual(len(response.json()["length_revision"]["attempts"]), 1)
        self.assertEqual(
            response.json()["strategy"]["central_idea"],
            "坚持需要明确目标和持续行动",
        )
        self.assertEqual(response.json()["strategy"]["structure"], "层进式论证")
        self.assertEqual(_create_essay.call_args.kwargs["essay"], revised_essay)
        self.assertEqual(mock_create.call_count, 2)

        model_request = mock_create.call_args_list[0].kwargs
        user_prompt = model_request["messages"][1]["content"]
        self.assertIn("作文材料：坚持不是重复", user_prompt)
        self.assertIn("文体要求：议论文", user_prompt)
        self.assertIn("目标字数：约 800 字", user_prompt)

        revision_prompt = mock_create.call_args_list[1].kwargs["messages"][1]["content"]
        self.assertIn("程序允许范围：750～850 字", revision_prompt)
        self.assertIn("至少增加约 769 个有效汉字", revision_prompt)
        self.assertIn("以约 830 字为写作目标", revision_prompt)
        self.assertIn("只输出修订后的完整作文正文", revision_prompt)

    @patch("backend.main.create_essay", return_value=RECORD)
    @patch("backend.main.get_user", return_value=USER)
    def test_generate_does_not_revise_acceptable_length(
        self, _get_user, _create_essay
    ) -> None:
        acceptable_essay = "《行而不辍》\n\n" + "行" * 794
        fake_model = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=f"【作文正文】\n{acceptable_essay}")
                )
            ]
        )
        with (
            patch.object(main, "API_KEY", "test-key"),
            patch.object(
                main.client.chat.completions,
                "create",
                return_value=fake_model,
            ) as mock_create,
        ):
            response = self.client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
                json={"topic": "论坚持", "target_word_count": 800},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["word_check"]["status"], "ok")
        self.assertFalse(response.json()["length_revision"]["attempted"])
        self.assertEqual(mock_create.call_count, 1)

    @patch("backend.main.create_essay", return_value=RECORD)
    @patch("backend.main.get_user", return_value=USER)
    def test_generate_can_correct_an_overlong_first_revision(
        self, _get_user, _create_essay
    ) -> None:
        initial_model = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="《行》\n\n" + "行" * 5))]
        )
        overlong_essay = "《行而不辍》\n\n" + "行" * 894
        overlong_model = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=overlong_essay))]
        )
        acceptable_essay = "《行而不辍》\n\n" + "行" * 794
        acceptable_model = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=acceptable_essay))]
        )
        with (
            patch.object(main, "API_KEY", "test-key"),
            patch.object(
                main.client.chat.completions,
                "create",
                side_effect=[initial_model, overlong_model, acceptable_model],
            ) as mock_create,
        ):
            response = self.client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
                json={"topic": "论坚持", "target_word_count": 800},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["word_check"]["actual"], 800)
        self.assertEqual(response.json()["word_check"]["status"], "ok")
        attempts = response.json()["length_revision"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["status"], "long")
        self.assertEqual(attempts[1]["status"], "ok")
        self.assertEqual(mock_create.call_count, 3)

    @patch("backend.main.get_user", return_value=USER)
    def test_generate_rejects_invalid_target_word_count(self, _get_user) -> None:
        response = self.client.post(
            "/api/generate",
            headers=AUTH_HEADERS,
            json={"topic": "论坚持", "target_word_count": 500},
        )
        self.assertEqual(response.status_code, 422)

    def test_model_output_without_markers_falls_back_to_essay(self) -> None:
        strategy, essay = main._parse_model_output(RECORD["essay"])
        self.assertIsNone(strategy)
        self.assertEqual(essay, RECORD["essay"])

    def test_word_count_uses_composition_grid_cells(self) -> None:
        self.assertEqual(main._count_words("《题》\n正文，继续。"), 9)

    def test_model_output_keeps_essay_when_strategy_marker_is_missing(self) -> None:
        strategy, essay = main._parse_model_output(
            f"中心立意：测试\n【作文正文】\n{RECORD['essay']}"
        )
        self.assertIsNone(strategy)
        self.assertEqual(essay, RECORD["essay"])

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
