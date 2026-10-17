"""Encrypted local secret storage for student-side API keys."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


PREFIX = "enc:v1:"


def _data_dir() -> Path:
    return Path(os.environ.get("STUDENT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


def _load_or_create_raw_secret() -> str:
    configured = os.environ.get("STUDENT_KEY_ENCRYPTION_SECRET", "").strip()
    if len(configured) >= 32:
        return configured
    secret_file = Path(os.environ.get("STUDENT_KEY_ENCRYPTION_SECRET_FILE", _data_dir() / ".student-key-secret"))
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = secret_file.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except FileNotFoundError:
        pass
    generated = secrets.token_urlsafe(48)
    try:
        fd = os.open(str(secret_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(generated)
        return generated
    except FileExistsError:
        existing = secret_file.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
        raise RuntimeError("学生端 Key 加密密钥文件内容无效，请删除后重启以重新生成")


def _fernet() -> Fernet:
    digest = hashlib.sha256(_load_or_create_raw_secret().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    value = str(value or "")
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def decrypt_config(config: dict | None) -> dict | None:
    if not config:
        return config
    result = dict(config)
    for key in ("api_key", "image_api_key", "embedding_api_key", "search_api_key", "jev_api_key"):
        if key in result:
            result[key] = decrypt_secret(result.get(key, ""))
    return result

