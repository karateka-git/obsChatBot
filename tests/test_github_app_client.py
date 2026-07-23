"""Тесты GitHub App HTTP adapter без реального интернета."""

from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

from obs_chat_bot.application.vaults.github_models import (
    GitHubDevicePollStatus,
    GitHubGatewayError,
    GitHubUserAccessToken,
)
from obs_chat_bot.data.github.github_app_client import UrllibGitHubAppClient
from obs_chat_bot.data.github.jwt_signer import PyJwtGitHubAppSigner


class FakeResponse:
    """Имитирует JSON-ответ `urlopen` как context manager."""

    def __init__(self, payload: dict | list) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        return None

    def read(self) -> bytes:
        """Возвращает сериализованный JSON payload."""
        return self._body


class GitHubAppClientTest(unittest.TestCase):
    """Проверяет Device Flow и installation token HTTP-контракты."""

    def test_request_device_authorization_uses_client_id_without_secret(self) -> None:
        """Первый Device Flow запрос передаёт только публичный Client ID."""
        payload = {
            "device_code": "device-secret",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            return_value=FakeResponse(payload),
        ) as opener:
            result = _client().request_device_authorization()

        request = opener.call_args.args[0]
        form = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(form, {"client_id": ["Iv1.client"]})
        self.assertEqual(result.user_code, "ABCD-EFGH")
        self.assertNotIn("device-secret", repr(result))

    def test_poll_device_token_maps_pending_slow_and_authorized(self) -> None:
        """GitHub error codes превращаются в типизированные статусы polling."""
        responses = [
            FakeResponse({"error": "authorization_pending"}),
            FakeResponse({"error": "slow_down"}),
            FakeResponse({"access_token": "ghu-secret", "token_type": "bearer"}),
        ]
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            side_effect=responses,
        ):
            client = _client()
            pending = client.poll_device_token("device-secret")
            slow = client.poll_device_token("device-secret")
            authorized = client.poll_device_token("device-secret")

        self.assertEqual(pending.status, GitHubDevicePollStatus.PENDING)
        self.assertEqual(slow.status, GitHubDevicePollStatus.SLOW_DOWN)
        self.assertEqual(authorized.status, GitHubDevicePollStatus.AUTHORIZED)
        self.assertEqual(authorized.access_token.value, "ghu-secret")
        self.assertNotIn("ghu-secret", repr(authorized))

    def test_list_installations_reads_all_pages(self) -> None:
        """Installation IDs читаются со всех страниц user endpoint."""
        first_page = [{"id": value} for value in range(1, 101)]
        second_page = [{"id": 101}]
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            side_effect=[
                FakeResponse({"total_count": 101, "installations": first_page}),
                FakeResponse({"total_count": 101, "installations": second_page}),
            ],
        ) as opener:
            installation_ids = _client().list_installation_ids(
                GitHubUserAccessToken("ghu-secret")
            )

        self.assertEqual(installation_ids, set(range(1, 102)))
        self.assertIn("page=2", opener.call_args_list[1].args[0].full_url)
        self.assertEqual(
            opener.call_args_list[0].args[0].get_header("Authorization"),
            "Bearer ghu-secret",
        )

    def test_get_authenticated_account_reads_public_id_and_login(self) -> None:
        """Авторизованный user endpoint определяет аккаунт без сохранения token."""
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            return_value=FakeResponse({"id": 777, "login": "octocat"}),
        ) as opener:
            account = _client().get_authenticated_account(
                GitHubUserAccessToken("ghu-secret")
            )

        request = opener.call_args.args[0]
        self.assertEqual(account.github_user_id, 777)
        self.assertEqual(account.login, "octocat")
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer ghu-secret")

    def test_create_installation_token_scopes_request_to_repository(self) -> None:
        """Installation token можно ограничить выбранным repository ID."""
        payload = {
            "token": "ghs-secret",
            "expires_at": "2026-07-22T12:00:00Z",
        }
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            return_value=FakeResponse(payload),
        ) as opener:
            token = _client().create_installation_token(
                installation_id=101,
                repository_id=501,
            )

        request = opener.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"repository_ids": [501]})
        self.assertEqual(request.get_header("Authorization"), "Bearer app-jwt")
        self.assertEqual(token.expires_at, datetime(2026, 7, 22, 12, 0, tzinfo=UTC))
        self.assertNotIn("ghs-secret", repr(token))

    def test_inspect_repository_checks_default_branch_and_vault_directory(self) -> None:
        """Repository inspection использует installation token и Contents API."""
        responses = [
            FakeResponse(
                {
                    "token": "ghs-secret",
                    "expires_at": "2026-07-23T12:00:00Z",
                }
            ),
            FakeResponse(
                {
                    "id": 501,
                    "name": "notes",
                    "owner": {"login": "octocat"},
                    "default_branch": "main",
                }
            ),
            FakeResponse([{"type": "file", "name": "Index.md"}]),
        ]
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            side_effect=responses,
        ) as opener:
            inspection = _client().inspect_repository(
                installation_id=101,
                owner="octocat",
                repository="notes",
                root_path="Vault/Личное",
            )

        self.assertEqual(inspection.repository_id, 501)
        self.assertEqual(inspection.default_branch, "main")
        self.assertTrue(inspection.root_path_is_directory)
        repository_request = opener.call_args_list[1].args[0]
        contents_request = opener.call_args_list[2].args[0]
        self.assertEqual(
            repository_request.full_url,
            "https://api.github.com/repos/octocat/notes",
        )
        self.assertIn(
            "Vault/%D0%9B%D0%B8%D1%87%D0%BD%D0%BE%D0%B5",
            contents_request.full_url,
        )
        self.assertIn("ref=main", contents_request.full_url)
        self.assertEqual(
            contents_request.get_header("Authorization"),
            "Bearer ghs-secret",
        )

    def test_inspect_repository_returns_none_on_not_found(self) -> None:
        """HTTP 404 означает, что installation не имеет указанного repository."""
        not_found = HTTPError(
            url="https://api.github.com/repos/octocat/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            side_effect=[
                FakeResponse(
                    {
                        "token": "ghs-secret",
                        "expires_at": "2026-07-23T12:00:00Z",
                    }
                ),
                not_found,
            ],
        ):
            inspection = _client().inspect_repository(
                installation_id=101,
                owner="octocat",
                repository="missing",
                root_path="",
            )

        self.assertIsNone(inspection)

    def test_http_error_does_not_include_response_or_token(self) -> None:
        """HTTP-ошибка сообщает только status и не раскрывает credentials."""
        error = HTTPError(
            url="https://api.github.com/user/installations",
            code=401,
            msg="token ghu-secret rejected",
            hdrs=None,
            fp=None,
        )
        with patch(
            "obs_chat_bot.data.github.github_app_client.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(GitHubGatewayError) as context:
                _client().list_installation_ids(GitHubUserAccessToken("ghu-secret"))

        self.assertEqual(str(context.exception), "GitHub request failed with HTTP 401")
        self.assertNotIn("ghu-secret", str(context.exception))

    def test_jwt_signer_uses_client_id_and_short_lifetime(self) -> None:
        """JWT signer использует рекомендуемый Client ID и окно меньше 10 минут."""
        now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
        calls: list[tuple[dict, bytes, str]] = []

        def encode(payload, key, algorithm):
            calls.append((payload, key, algorithm))
            return "signed-jwt"

        fake_jwt = types.SimpleNamespace(encode=encode)
        with TemporaryDirectory(prefix="obs-chat-bot-github-jwt-") as directory:
            key_path = Path(directory) / "app.pem"
            key_path.write_bytes(b"private-key")
            with patch.dict("sys.modules", {"jwt": fake_jwt}):
                result = PyJwtGitHubAppSigner(
                    client_id="Iv1.client",
                    private_key_path=key_path,
                    clock=lambda: now,
                ).create()

        payload, key, algorithm = calls[0]
        self.assertEqual(result, "signed-jwt")
        self.assertEqual(payload["iss"], "Iv1.client")
        self.assertLessEqual(payload["exp"] - payload["iat"], 600)
        self.assertEqual(key, b"private-key")
        self.assertEqual(algorithm, "RS256")

    def test_jwt_signer_creates_verifiable_rs256_signature(self) -> None:
        """Реальные PyJWT и cryptography подписывают JWT временным RSA-ключом."""
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with TemporaryDirectory(prefix="obs-chat-bot-github-rs256-") as directory:
            key_path = Path(directory) / "app.pem"
            key_path.write_bytes(private_pem)
            token = PyJwtGitHubAppSigner(
                client_id="Iv1.client",
                private_key_path=key_path,
            ).create()

        payload = jwt.decode(
            token,
            private_key.public_key(),
            algorithms=["RS256"],
            options={"verify_exp": False, "verify_iat": False},
        )
        self.assertEqual(payload["iss"], "Iv1.client")


def _client() -> UrllibGitHubAppClient:
    """Создаёт HTTP client с предсказуемым App JWT."""
    return UrllibGitHubAppClient(
        client_id="Iv1.client",
        app_jwt_factory=lambda: "app-jwt",
    )


if __name__ == "__main__":
    unittest.main()
