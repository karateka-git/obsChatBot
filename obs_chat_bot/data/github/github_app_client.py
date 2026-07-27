from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from obs_chat_bot.application.vaults.github_models import (
    GitHubAuthenticatedAccount,
    GitHubDeviceAuthorization,
    GitHubDevicePollResult,
    GitHubDevicePollStatus,
    GitHubGatewayError,
    GitHubInstallationAccessToken,
    GitHubRepositoryInspection,
    GitHubMarkdownFile,
    GitHubUserAccessToken,
    GitHubVaultSnapshot,
    GitHubVaultSnapshotStatus,
)
from obs_chat_bot.application.vaults.ports import (
    GitHubDeviceFlowGateway,
    GitHubInstallationTokenProvider,
    GitHubRepositoryGateway,
    GitHubVaultGateway,
)
from obs_chat_bot.domain.vaults.entities import ObsidianVault


GITHUB_API_VERSION = "2026-03-10"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_WEB_BASE_URL = "https://github.com"
GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "obsChatBot/0.1.0"
DEFAULT_TIMEOUT_SECONDS = 15
MAX_BLOB_DOWNLOAD_WORKERS = 6  # Ограничивает параллелизм первой синхронизации.


class UrllibGitHubAppClient(
    GitHubDeviceFlowGateway,
    GitHubInstallationTokenProvider,
    GitHubRepositoryGateway,
    GitHubVaultGateway,
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

    def inspect_repository(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        root_path: str,
    ) -> GitHubRepositoryInspection | None:
        """Проверяет доступ installation к repository и каталогу vault.

        Args:
            installation_id: Разрешённая пользователю установка GitHub App.
            owner: Владелец repository.
            repository: Имя repository.
            root_path: Относительный путь каталога vault или пустая строка.

        Returns:
            Metadata repository и признак каталога либо `None` при HTTP 404.

        Raises:
            GitHubGatewayError: GitHub недоступен или вернул некорректный ответ.
        """
        if installation_id <= 0:
            raise ValueError("installation_id must be positive")
        if not owner.strip() or not repository.strip():
            raise ValueError("owner and repository must not be empty")
        token = self._create_repository_write_token(
            installation_id=installation_id,
            owner=owner,
            repository=repository,
        )
        if token is None:
            return None
        encoded_owner = quote(owner, safe="")
        encoded_repository = quote(repository, safe="")
        repository_payload = self._request_json_or_none(
            Request(
                f"{GITHUB_API_BASE_URL}/repos/{encoded_owner}/{encoded_repository}",
                headers=self._api_headers(token.value),
                method="GET",
            )
        )
        if repository_payload is None:
            return None
        if repository_payload.get("archived") is True:
            return None
        if repository_payload.get("disabled") is True:
            return None

        repository_id = _require_positive_int(repository_payload, "id")
        canonical_owner = _require_nested_string(
            repository_payload,
            container_name="owner",
            field_name="login",
        )
        canonical_repository = _require_string(repository_payload, "name")
        default_branch = _require_string(repository_payload, "default_branch")
        encoded_path = quote(root_path, safe="/")
        contents_suffix = f"/{encoded_path}" if encoded_path else ""
        query = urlencode({"ref": default_branch})
        contents_payload = self._request_json_value(
            Request(
                f"{GITHUB_API_BASE_URL}/repos/{encoded_owner}/"
                f"{encoded_repository}/contents{contents_suffix}?{query}",
                headers=self._api_headers(token.value),
                method="GET",
            ),
            allow_not_found=True,
        )
        return GitHubRepositoryInspection(
            installation_id=installation_id,
            repository_id=repository_id,
            owner=canonical_owner,
            repository=canonical_repository,
            default_branch=default_branch,
            root_path_is_directory=isinstance(contents_payload, list),
        )

    def fetch_vault_snapshot(
        self,
        vault: ObsidianVault,
        *,
        known_blobs: Mapping[str, str],
    ) -> GitHubVaultSnapshot:
        """Читает Git tree vault и скачивает только неизвестные Markdown blobs.

        Args:
            vault: Сохраненное подключение repository, ветки и корневой папки.
            known_blobs: Локальное соответствие пути и последнего blob SHA.

        Returns:
            Условный снимок с полным manifest и содержимым изменённых файлов.

        Raises:
            GitHubGatewayError: GitHub недоступен или вернул некорректные данные.
        """
        token = self.create_installation_token(
            installation_id=vault.installation_id,
            repository_id=vault.repository_id,
        )
        repository_url = (
            f"{GITHUB_API_BASE_URL}/repos/{quote(vault.owner, safe='')}/"
            f"{quote(vault.repository, safe='')}"
        )
        ref_headers = self._api_headers(token.value)
        if vault.head_etag is not None:
            ref_headers["If-None-Match"] = vault.head_etag
        ref_payload, ref_etag, not_modified = self._request_json_with_metadata(
            Request(
                f"{repository_url}/git/ref/heads/{quote(vault.branch, safe='')}",
                headers=ref_headers,
                method="GET",
            ),
            allow_not_modified=True,
        )
        if not_modified:
            return GitHubVaultSnapshot(
                status=GitHubVaultSnapshotStatus.NOT_MODIFIED,
                head_etag=vault.head_etag,
            )
        head_commit_sha = _require_nested_string(
            ref_payload,
            container_name="object",
            field_name="sha",
        )
        commit_payload = self._request_json(
            Request(
                f"{repository_url}/git/commits/{quote(head_commit_sha, safe='')}",
                headers=self._api_headers(token.value),
                method="GET",
            )
        )
        repository_tree_sha = _require_nested_string(
            commit_payload,
            container_name="tree",
            field_name="sha",
        )
        vault_tree_sha = self._resolve_vault_tree_sha(
            repository_url=repository_url,
            token=token.value,
            tree_sha=repository_tree_sha,
            root_path=vault.root_path,
        )
        if vault.tree_sha == vault_tree_sha:
            return GitHubVaultSnapshot(
                status=GitHubVaultSnapshotStatus.TREE_UNCHANGED,
                head_commit_sha=head_commit_sha,
                tree_sha=vault_tree_sha,
                head_etag=ref_etag,
            )

        tree_payload = self._request_json(
            Request(
                f"{repository_url}/git/trees/{quote(vault_tree_sha, safe='')}"
                "?recursive=1",
                headers=self._api_headers(token.value),
                method="GET",
            )
        )
        if tree_payload.get("truncated") is True:
            raise GitHubGatewayError("GitHub vault tree is truncated")
        tree = tree_payload.get("tree")
        if not isinstance(tree, list):
            raise GitHubGatewayError("GitHub tree response has unexpected format")
        manifest: list[tuple[str, str]] = []
        for item in tree:
            if not isinstance(item, dict) or item.get("type") != "blob":
                continue
            path = item.get("path")
            blob_sha = item.get("sha")
            if (
                not isinstance(path, str)
                or not path.lower().endswith(".md")
                or not isinstance(blob_sha, str)
                or not blob_sha.strip()
            ):
                continue
            manifest.append((path, blob_sha))
        changed = [
            (path, blob_sha)
            for path, blob_sha in manifest
            if known_blobs.get(path) != blob_sha
        ]
        downloaded: dict[str, str] = {}
        if changed:
            with ThreadPoolExecutor(
                max_workers=min(MAX_BLOB_DOWNLOAD_WORKERS, len(changed))
            ) as executor:
                contents = executor.map(
                    lambda item: self._download_markdown_blob(
                        repository_url=repository_url,
                        token=token.value,
                        blob_sha=item[1],
                    ),
                    changed,
                )
                downloaded = {
                    path: markdown
                    for (path, _blob_sha), markdown in zip(changed, contents)
                }
        files = [
            GitHubMarkdownFile(
                path=path,
                blob_sha=blob_sha,
                markdown=downloaded.get(path),
            )
            for path, blob_sha in manifest
        ]
        return GitHubVaultSnapshot(
            status=GitHubVaultSnapshotStatus.CHANGED,
            head_commit_sha=head_commit_sha,
            tree_sha=vault_tree_sha,
            head_etag=ref_etag,
            files=tuple(sorted(files, key=lambda file: file.path)),
        )

    def _resolve_vault_tree_sha(
        self,
        *,
        repository_url: str,
        token: str,
        tree_sha: str,
        root_path: str,
    ) -> str:
        current_sha = tree_sha
        for segment in root_path.split("/") if root_path else ():
            payload = self._request_json(
                Request(
                    f"{repository_url}/git/trees/{quote(current_sha, safe='')}",
                    headers=self._api_headers(token),
                    method="GET",
                )
            )
            entries = payload.get("tree")
            if not isinstance(entries, list):
                raise GitHubGatewayError(
                    "GitHub tree response has unexpected format"
                )
            match = next(
                (
                    item
                    for item in entries
                    if isinstance(item, dict)
                    and item.get("type") == "tree"
                    and item.get("path") == segment
                ),
                None,
            )
            if match is None or not isinstance(match.get("sha"), str):
                raise GitHubGatewayError("GitHub vault path no longer exists")
            current_sha = match["sha"]
        return current_sha

    def _download_markdown_blob(
        self,
        *,
        repository_url: str,
        token: str,
        blob_sha: str,
    ) -> str:
        payload = self._request_json(
            Request(
                f"{repository_url}/git/blobs/{quote(blob_sha, safe='')}",
                headers=self._api_headers(token),
                method="GET",
            )
        )
        if payload.get("encoding") != "base64":
            raise GitHubGatewayError("GitHub blob encoding is not base64")
        encoded = _require_string_allow_empty(payload, "content")
        try:
            return base64.b64decode(encoded, validate=False).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise GitHubGatewayError("GitHub Markdown blob is invalid") from error

    def _create_repository_write_token(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
    ) -> GitHubInstallationAccessToken | None:
        """Выпускает token записи, ограниченный конкретным repository.

        GitHub отклоняет запрос, если repository не входит в installation или
        installation не получила `Contents: write`. Выданный token дополнительно
        содержит repository, на который он ограничен: это позволяет сверить полный
        owner/name, даже если одинаковое имя есть у разных владельцев.
        """
        body = {
            "repositories": [repository],
            "permissions": {
                "contents": "write",
                "metadata": "read",
            },
        }
        app_jwt = self._app_jwt_factory()
        payload = self._request_json_or_none(
            Request(
                f"{GITHUB_API_BASE_URL}/app/installations/"
                f"{installation_id}/access_tokens",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    **self._api_headers(app_jwt),
                    "Content-Type": "application/json",
                },
                method="POST",
            ),
            absent_statuses=frozenset({403, 404, 422}),
        )
        if payload is None:
            return None
        permissions = payload.get("permissions")
        if not isinstance(permissions, dict):
            raise GitHubGatewayError(
                "GitHub installation token permissions have unexpected format"
            )
        if permissions.get("contents") != "write":
            return None
        repositories = payload.get("repositories")
        if not isinstance(repositories, list):
            raise GitHubGatewayError(
                "GitHub installation token repositories have unexpected format"
            )
        expected_full_name = f"{owner}/{repository}".casefold()
        granted_full_names = {
            item.get("full_name").casefold()
            for item in repositories
            if isinstance(item, dict)
            and isinstance(item.get("full_name"), str)
        }
        if expected_full_name not in granted_full_names:
            return None
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
        payload = self._request_json_value(request)
        if not isinstance(payload, dict):
            raise GitHubGatewayError("GitHub response is not a JSON object")
        return payload

    def _request_json_with_metadata(
        self,
        request: Request,
        *,
        allow_not_modified: bool,
    ) -> tuple[dict[str, Any], str | None, bool]:
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                headers = getattr(response, "headers", None)
                etag = headers.get("ETag") if headers is not None else None
        except HTTPError as error:
            if allow_not_modified and error.code == 304:
                return {}, None, True
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
        return payload, etag, False

    def _request_json_or_none(
        self,
        request: Request,
        *,
        absent_statuses: frozenset[int] = frozenset({404}),
    ) -> dict[str, Any] | None:
        payload = self._request_json_value(
            request,
            absent_statuses=absent_statuses,
        )
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise GitHubGatewayError("GitHub response is not a JSON object")
        return payload

    def _request_json_value(
        self,
        request: Request,
        *,
        allow_not_found: bool = False,
        absent_statuses: frozenset[int] = frozenset(),
    ) -> Any | None:
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if (allow_not_found and error.code == 404) or (
                error.code in absent_statuses
            ):
                return None
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
        return payload


def _require_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GitHubGatewayError(f"GitHub response field is invalid: {name}")
    return value


def _require_string_allow_empty(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
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


def _require_nested_string(
    payload: dict[str, Any],
    *,
    container_name: str,
    field_name: str,
) -> str:
    container = payload.get(container_name)
    if not isinstance(container, dict):
        raise GitHubGatewayError(
            f"GitHub response field is invalid: {container_name}"
        )
    return _require_string(container, field_name)


def _parse_github_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GitHubGatewayError("GitHub timestamp has unexpected format") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
