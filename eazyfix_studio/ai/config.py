"""Provider configuration and OS-backed credential storage."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4


class AISettingsError(RuntimeError):
    pass


class SecureStorageError(AISettingsError):
    pass


@dataclass
class AISettings:
    provider: str = "offline"
    endpoint: str = "https://api.deepseek.com"
    text_model: str = "deepseek-v4-pro"
    vision_model: str = "deepseek-flash"
    allow_project_context: bool = False

    def validate(self) -> None:
        if self.provider not in {"offline", "deepseek"}:
            raise AISettingsError("Unknown AI provider.")
        parts = urlsplit(self.endpoint.strip())
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise AISettingsError("Enter a valid AI API endpoint URL.")
        secure = parts.scheme == "https"
        loopback = parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if not (secure or loopback):
            raise AISettingsError("The API endpoint must use HTTPS (HTTP is allowed only for localhost).")
        if len(self.text_model.strip()) > 100 or len(self.vision_model.strip()) > 100:
            raise AISettingsError("Model names must be shorter than 100 characters.")
        if not self.text_model.strip() or not self.vision_model.strip():
            raise AISettingsError("Choose a text model and a vision model.")


def settings_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return root / "EazyFixAIStudio" / "settings.json"


class AISettingsStore:
    def load(self) -> AISettings:
        path = settings_path()
        if not path.exists():
            return AISettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = AISettings(
                provider=str(data.get("provider", "offline")),
                endpoint=str(data.get("endpoint", "https://api.deepseek.com")),
                text_model=str(data.get("text_model", "deepseek-v4-pro")),
                vision_model=str(data.get("vision_model", "deepseek-flash")),
                allow_project_context=bool(data.get("allow_project_context", False)),
            )
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise AISettingsError("AI settings could not be read. Open AI Settings and save a new configuration.") from error

    def save(self, settings: AISettings) -> None:
        settings.validate()
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()


class SecureKeyStore:
    """Use Windows Credential Manager through keyring; never fall back to plaintext."""

    SERVICE = "EazyFix AI Video Studio / DeepSeek"
    USERNAME = "api-key"

    @staticmethod
    def _keyring_module():
        try:
            import keyring
        except ImportError as error:
            raise SecureStorageError("Secure credential storage is unavailable. Install the application requirements and retry.") from error
        backend = keyring.get_keyring()
        module_name = type(backend).__module__.casefold()
        class_name = type(backend).__name__.casefold()
        if "fail" in module_name or "plaintext" in module_name or "null" in class_name:
            raise SecureStorageError("No secure operating-system credential store is available; the API key was not saved.")
        if sys.platform == "win32" and "windows" not in module_name:
            raise SecureStorageError("Windows Credential Manager is unavailable; the API key was not saved in a file.")
        return keyring

    def get(self) -> str | None:
        keyring = self._keyring_module()
        try:
            return keyring.get_password(self.SERVICE, self.USERNAME)
        except Exception as error:
            raise SecureStorageError("Could not read the API key from the operating-system credential store.") from error

    def set(self, api_key: str) -> None:
        api_key = api_key.strip()
        if not api_key or len(api_key) > 512:
            raise SecureStorageError("Enter a valid API key.")
        keyring = self._keyring_module()
        try:
            keyring.set_password(self.SERVICE, self.USERNAME, api_key)
        except Exception as error:
            raise SecureStorageError("Could not save the API key to the operating-system credential store.") from error

    def delete(self) -> None:
        keyring = self._keyring_module()
        try:
            keyring.delete_password(self.SERVICE, self.USERNAME)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as error:
            raise SecureStorageError("Could not remove the API key from the operating-system credential store.") from error
