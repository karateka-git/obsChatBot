from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from obs_chat_bot.application.vaults.github_models import (
    GitHubAuthenticatedAccount,
    GitHubDeviceAuthorization,
    GitHubDevicePollResult,
    GitHubDevicePollStatus,
    GitHubGatewayError,
    GitHubInstallationAccessToken,
    GitHubUserAccessToken,
)
from obs_chat_bot.application.vaults.ports import (
    GitHubDeviceFlowGateway,
    GitHubInstallationTokenProvider,
)


GITHUB_API_VERSION = "2026-03-10"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_WEB_BASE_URL = "https://github.com"
GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "obsChatBot/0.1.0"
DEFAULT_TIMEOUT_SECONDS = 15


class UrllibGitHubAppClient(
    GitHubDeviceFlowGateway,
    GitHubInstallationTokenProvider,
):
    """Выполняет GitHub Device Flow и выпускает installation tokens."""

    def __init__(
        self,
        *,
        client_id: str,
        app_jwt_factory: Callable[[], str],
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not client_id.strip():
            raise ValueError("client_id must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client_id = client_id
        self._app_jwt_factory = app_jwt_factory
        self._timeout_seconds = timeout_seconds

    def request_device_authorization(self) -> GitHubDeviceAuthorization:
        """Запрашивает Device Flow challenge по Client ID GitHub App."""
        payload = self._post_form(
            f"{GITHUB_WEB_BASE_URL}/login/device/code",
            {"client_id": self._client_id},
        )
        return GitHubDeviceAuthorization(
            device_code=_require_string(payload, "device_code"),
            user_code=_require_string(payload, "user_code"),
            verification_uri=_require_string(payload, "verification_uri"),
            expires_in=_require_positive_int(payload, "expires_in"),
            interval=_require_positive_int(payload, "interval"),
        )

    def poll_device_token(self, device_code: str) -> GitHubDevicePollResult:
        """Проверяет одно состояние Device Flow без внутреннего ожидания."""
        if not device_code.strip():
            raise ValueError("device_code must not be empty")
        payload = self._post_form(
            f"{GITHUB_WEB_BASE_URL}/login/oauth/access_token",
            {
                "client_id": self._client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        access_token = payload.get("access_token")
        if isinstance(access_token, str) and access_token.strip():
            return GitHubDevicePollResult(
                status=GitHubDevicePollStatus.AUTHORIZED,
                access_token=GitHubUserAccessToken(access_token),
            )

        error = payload.get("error")
        statuses = {
            "authorization_pending": GitHubDevicePollStatus.PENDING,
            "slow_down": GitHubDevicePollStatus.SLOW_DOWN,
            "expired_token": GitHubDevicePollStatus.EXPIRED,
            "access_denied": GitHubDevicePollStatus.DENIED,
        }
        if isinstance(error, str) and error in statuses:
            return GitHubDevicePollResult(status=statuses[error])
        raise GitHubGatewayError("GitHub Device Flow returned an unknown response")

    def list_installation_ids(
        self,
        access_token: GitHubUserAccessToken,
    ) -> set[int]:
        """Читает все доступные installations с пагинацией по 100 строк."""
        installation_ids: set[int] = set()
        page = 1
        while True:
            query = urlencode({"per_page": 100, "page": page})
            payload = self._request_json(
                Request(
                    f"{GITHUB_API_BASE_URL}/user/installations?{query}",
                    headers=self._api_headers(access_token.value),
                    method="GET",
                )
            )
            installations = payload.get("installations")
            if not isinstance(installations, list):
                raise GitHubGatewayError(
                    "GitHub installations response has unexpected format"
                )
            for installation in installations:
                if not isinstance(installation, dict):
                    raise GitHubGatewayError(
                        "GitHub installation item has unexpected format"
                    )
                installation_ids.add(_require_positive_int(installation, "id"))

            total_count = _require_non_negative_int(payload, "total_count")
            if len(installations) < 100 or len(installation_ids) >= total_count:
                return installation_ids
            page += 1

    def get_authenticated_account(
        self,
        access_token: GitHubUserAccessToken,
    ) -> GitHubAuthenticatedAccount:
        """Читает публичные ID и login авторизованного GitHub-аккаунта."""
        payload = self._request_json(
            Request(
                f"{GITHUB_API_BASE_URL}/user",
                headers=self._api_headers(access_token.value),
                method="GET",
            )
        )
        return GitHubAuthenticatedAccount(
            github_user_id=_require_positive_int(payload, "id"),
            login=_require_string(payload, "login"),
        )

    def create_installation_token(
        self,
        *,
        installation_id: int,
        repository_id: int | None = None,
    ) -> GitHubInstallationAccessToken:
        """Выпускает installation token, опционально ограниченный repository."""
        if installation_id <= 0:
            raise ValueError("installation_id must be positive")
        if repository_id is not None and repository_id <= 0:
            raise ValueError("repository_id must be positive")
        body: dict[str, Any] = {}
        if repository_id is not None:
            body["repository_ids"] = [repository_id]
        app_jwt = self._app_jwt_factory()
        payload = self._request_json(
            Request(
                f"{GITHUB_API_BASE_URL}/app/installations/"
                f"{installation_id}/access_tokens",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    **self._api_headers(app_jwt),
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        )
        return GitHubInstallationAccessToken(
            value=_require_string(payload, "token"),
            expires_at=_parse_github_timestamp(
                _require_string(payload, "expires_at")
            ),
        )

    def _post_form(self, url: str, values: dict[str, str]) -> dict[str, Any]:
        return self._request_json(
            Request(
                url,
                data=urlencode(values).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": GITHUB_USER_AGENT,
                },
                method="POST",
            )
        )

    def _api_headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": GITHUB_ACCEPT,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": GITHUB_USER_AGENT,
        }

    def _request_json(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise GitHubGatewayError(
                f"GitHub request failed with HTTP {error.code}"
            ) from error
        except (
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise GitHubGatewayError(
                f"GitHub request failed: {type(error).__name__}"
            ) from error
        if not isinstance(payload, dict):
            raise GitHubGatewayError("GitHub response is not a JSON object")
        return payload


def _require_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GitHubGatewayError(f"GitHub response field is invalid: {name}")
    return value


def _require_positive_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise GitHubGatewayError(f"GitHub response field is invalid: {name}")
    return value


def _require_non_negative_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GitHubGatewayError(f"GitHub response field is invalid: {name}")
    return value


def _parse_github_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GitHubGatewayError("GitHub timestamp has unexpected format") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
