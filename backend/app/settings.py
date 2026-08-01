from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass


FRED_KEY_PATTERN = re.compile(r"^[a-z0-9]{32}$")
AIHUBMIX_KEY_PATTERN = re.compile(r"^sk-[A-Za-z0-9_-]{20,200}$")


@dataclass(frozen=True)
class SecretStatus:
    configured: bool
    source: str


class FredSecretStore:
    """Keep the user-owned FRED key outside databases and API responses."""

    service_name = "com.akdesk.fixed.fred-api-key"

    def __init__(self) -> None:
        self._keychain_loaded = False
        self._cached_key: str | None = None

    def get(self) -> str | None:
        environment = (
            os.getenv("AKDESK_FRED_API_KEY") or os.getenv("FRED_API_KEY") or ""
        ).strip()
        if FRED_KEY_PATTERN.fullmatch(environment):
            return environment
        if self._keychain_loaded:
            return self._cached_key
        if sys.platform != "darwin":
            self._keychain_loaded = True
            return None
        security = shutil.which("security")
        if not security:
            self._keychain_loaded = True
            return None
        try:
            result = subprocess.run(
                [
                    security,
                    "find-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            self._keychain_loaded = True
            return None
        key = result.stdout.strip() if result.returncode == 0 else ""
        self._cached_key = key if FRED_KEY_PATTERN.fullmatch(key) else None
        self._keychain_loaded = True
        return self._cached_key

    def status(self) -> SecretStatus:
        environment = (
            os.getenv("AKDESK_FRED_API_KEY") or os.getenv("FRED_API_KEY") or ""
        ).strip()
        if FRED_KEY_PATTERN.fullmatch(environment):
            return SecretStatus(configured=True, source="environment")
        key = self.get()
        return SecretStatus(
            configured=key is not None,
            source="keychain" if key is not None else "none",
        )

    def set(self, api_key: str) -> None:
        if not FRED_KEY_PATTERN.fullmatch(api_key):
            raise ValueError("FRED API Key 应为 32 位小写字母或数字")
        if sys.platform != "darwin":
            raise RuntimeError("当前系统不支持 macOS Keychain，请使用 AKDESK_FRED_API_KEY")
        security = shutil.which("security")
        if not security:
            raise RuntimeError("未找到 macOS security 工具")
        try:
            result = subprocess.run(
                [
                    security,
                    "add-generic-password",
                    "-U",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                input=f"{api_key}\n{api_key}\n",
                timeout=10,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("FRED API Key 写入 Keychain 失败") from exc
        if result.returncode != 0:
            raise RuntimeError("FRED API Key 写入 Keychain 失败")
        self._cached_key = api_key
        self._keychain_loaded = True

    def delete(self) -> bool:
        if sys.platform != "darwin":
            return False
        security = shutil.which("security")
        if not security:
            return False
        try:
            result = subprocess.run(
                [
                    security,
                    "delete-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        deleted = result.returncode == 0
        if deleted:
            self._cached_key = None
            self._keychain_loaded = True
        return deleted


class AiHubMixSecretStore:
    """Keep the user-owned AIHubMix key outside databases and API responses."""

    service_name = "com.akdesk.fixed.aihubmix-api-key"

    def __init__(self) -> None:
        self._keychain_loaded = False
        self._cached_key: str | None = None

    @staticmethod
    def _environment_key() -> str:
        return (
            os.getenv("AKDESK_AIHUBMIX_API_KEY")
            or os.getenv("AIHUBMIX_API_KEY")
            or ""
        ).strip()

    def get(self) -> str | None:
        environment = self._environment_key()
        if AIHUBMIX_KEY_PATTERN.fullmatch(environment):
            return environment
        if self._keychain_loaded:
            return self._cached_key
        if sys.platform != "darwin":
            self._keychain_loaded = True
            return None
        security = shutil.which("security")
        if not security:
            self._keychain_loaded = True
            return None
        try:
            result = subprocess.run(
                [
                    security,
                    "find-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            self._keychain_loaded = True
            return None
        key = result.stdout.strip() if result.returncode == 0 else ""
        self._cached_key = key if AIHUBMIX_KEY_PATTERN.fullmatch(key) else None
        self._keychain_loaded = True
        return self._cached_key

    def status(self) -> SecretStatus:
        environment = self._environment_key()
        if AIHUBMIX_KEY_PATTERN.fullmatch(environment):
            return SecretStatus(configured=True, source="environment")
        key = self.get()
        return SecretStatus(
            configured=key is not None,
            source="keychain" if key is not None else "none",
        )

    def set(self, api_key: str) -> None:
        if not AIHUBMIX_KEY_PATTERN.fullmatch(api_key):
            raise ValueError("AIHubMix API Key 格式无效")
        if sys.platform != "darwin":
            raise RuntimeError(
                "当前系统不支持 macOS Keychain，请使用 AKDESK_AIHUBMIX_API_KEY"
            )
        security = shutil.which("security")
        if not security:
            raise RuntimeError("未找到 macOS security 工具")
        try:
            result = subprocess.run(
                [
                    security,
                    "add-generic-password",
                    "-U",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                    "-w",
                ],
                check=False,
                capture_output=True,
                text=True,
                input=f"{api_key}\n{api_key}\n",
                timeout=10,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("AIHubMix API Key 写入 Keychain 失败") from exc
        if result.returncode != 0:
            raise RuntimeError("AIHubMix API Key 写入 Keychain 失败")
        self._cached_key = api_key
        self._keychain_loaded = True

    def delete(self) -> bool:
        if sys.platform != "darwin":
            return False
        security = shutil.which("security")
        if not security:
            return False
        try:
            result = subprocess.run(
                [
                    security,
                    "delete-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    self.service_name,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        deleted = result.returncode == 0
        if deleted:
            self._cached_key = None
            self._keychain_loaded = True
        return deleted
