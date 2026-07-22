from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
from threading import Lock, Thread
import time

from obs_chat_bot.application.vaults.github_models import (
    GitHubConnectionStartResult,
    GitHubConnectionStartStatus,
    GitHubDeviceAuthorization,
    GitHubDevicePollStatus,
    GitHubGatewayError,
    GitHubUserAccessToken,
)
from obs_chat_bot.application.vaults.ports import (
    GitHubConnectionStarter,
    GitHubDeviceFlowGateway,
    GitHubInstallationAccessWriter,
)


LOGGER = logging.getLogger(__name__)


class GitHubConnectionCoordinator(GitHubConnectionStarter):
    """Координирует Device Flow в памяти и сохраняет только installation IDs."""

    def __init__(
        self,
        *,
        gateway: GitHubDeviceFlowGateway,
        installation_writer: GitHubInstallationAccessWriter,
        installation_url: str,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        thread_factory: Callable[..., Thread] | None = None,
    ) -> None:
        if not installation_url.strip():
            raise ValueError("installation_url must not be empty")
        self._gateway = gateway
        self._installation_writer = installation_writer
        self._installation_url = installation_url
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper or time.sleep
        self._thread_factory = thread_factory or Thread
        self._sessions: dict[int, GitHubDeviceAuthorization | None] = {}
        self._lock = Lock()

    def start(self, app_user_id: int) -> GitHubConnectionStartResult:
        """Возвращает challenge немедленно и запускает polling в daemon thread."""
        if app_user_id <= 0:
            raise ValueError("app_user_id must be positive")
        with self._lock:
            if app_user_id in self._sessions:
                authorization = self._sessions[app_user_id]
                status = (
                    GitHubConnectionStartStatus.ALREADY_PENDING
                    if authorization is not None
                    else GitHubConnectionStartStatus.PREPARING
                )
                return GitHubConnectionStartResult(
                    status=status,
                    installation_url=self._installation_url,
                    authorization=authorization,
                )
            self._sessions[app_user_id] = None

        authorization: GitHubDeviceAuthorization | None = None
        try:
            authorization = self._gateway.request_device_authorization()
            with self._lock:
                self._sessions[app_user_id] = authorization
            worker = self._thread_factory(
                target=self._poll_until_complete,
                args=(app_user_id, authorization),
                name=f"github-device-flow-{app_user_id}",
                daemon=True,
            )
            worker.start()
        except Exception as error:
            self._remove_session(app_user_id, expected=authorization)
            if isinstance(error, GitHubGatewayError):
                raise
            raise GitHubGatewayError(
                f"GitHub Device Flow could not start: {type(error).__name__}"
            ) from error

        return GitHubConnectionStartResult(
            status=GitHubConnectionStartStatus.STARTED,
            installation_url=self._installation_url,
            authorization=authorization,
        )

    def _poll_until_complete(
        self,
        app_user_id: int,
        authorization: GitHubDeviceAuthorization,
    ) -> None:
        deadline = self._clock() + timedelta(seconds=authorization.expires_in)
        interval = float(authorization.interval)
        try:
            while self._clock() < deadline:
                self._sleeper(interval)
                if self._clock() >= deadline:
                    break
                try:
                    result = self._gateway.poll_device_token(
                        authorization.device_code
                    )
                except GitHubGatewayError as error:
                    LOGGER.warning(
                        "GitHub Device Flow poll failed for app_user_id=%s: %s",
                        app_user_id,
                        error,
                    )
                    continue

                if result.status is GitHubDevicePollStatus.PENDING:
                    continue
                if result.status is GitHubDevicePollStatus.SLOW_DOWN:
                    interval += 5
                    continue
                if result.status is GitHubDevicePollStatus.AUTHORIZED:
                    self._complete_authorization(app_user_id, result.access_token)
                    return
                if result.status is GitHubDevicePollStatus.DENIED:
                    LOGGER.info(
                        "GitHub Device Flow denied for app_user_id=%s",
                        app_user_id,
                    )
                    return
                if result.status is GitHubDevicePollStatus.EXPIRED:
                    break

            LOGGER.info(
                "GitHub Device Flow expired for app_user_id=%s",
                app_user_id,
            )
        finally:
            self._remove_session(app_user_id, expected=authorization)

    def _complete_authorization(
        self,
        app_user_id: int,
        access_token: GitHubUserAccessToken | None,
    ) -> None:
        if access_token is None:
            raise RuntimeError("Authorized Device Flow returned no access token")
        try:
            installation_ids = self._gateway.list_installation_ids(access_token)
            self._installation_writer.replace_for_user(
                app_user_id=app_user_id,
                installation_ids=installation_ids,
            )
        except GitHubGatewayError as error:
            LOGGER.warning(
                "GitHub installations could not be saved for app_user_id=%s: %s",
                app_user_id,
                error,
            )
            return
        except Exception as error:
            LOGGER.error(
                "GitHub installation storage failed for app_user_id=%s "
                "error_type=%s",
                app_user_id,
                type(error).__name__,
            )
            return
        LOGGER.info(
            "GitHub Device Flow completed: app_user_id=%s installation_count=%s",
            app_user_id,
            len(installation_ids),
        )

    def _remove_session(
        self,
        app_user_id: int,
        *,
        expected: GitHubDeviceAuthorization | None,
    ) -> None:
        with self._lock:
            current = self._sessions.get(app_user_id)
            if current is expected:
                self._sessions.pop(app_user_id, None)
