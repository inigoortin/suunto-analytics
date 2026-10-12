"""Opt-in credential storage in the OS keychain (macOS Keychain via `keyring`).

Only used to log in again when the saved session expires. Nothing is written to disk by us.
"""

from __future__ import annotations

from typing import Protocol

import keyring

SERVICE = "suunto-analytics"
_EMAIL_SLOT = "__email__"


class Backend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class CredentialStore:
    def __init__(self, backend: Backend = keyring):  # type: ignore[assignment]
        self._kr = backend

    def email(self) -> str | None:
        return self._kr.get_password(SERVICE, _EMAIL_SLOT)

    def get(self) -> tuple[str, str] | None:
        email = self.email()
        pw = self._kr.get_password(SERVICE, email) if email else None
        return (email, pw) if email and pw else None

    def save(self, email: str, password: str) -> None:
        self._kr.set_password(SERVICE, _EMAIL_SLOT, email)
        self._kr.set_password(SERVICE, email, password)

    def forget(self) -> None:
        email = self.email()
        for user in filter(None, (email, _EMAIL_SLOT)):
            try:
                self._kr.delete_password(SERVICE, user)
            except Exception:  # already absent
                pass
