"""Managed 致知 Workspace path, version, and text policies."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator

from zhizhi_platform.workspace.errors import UnsupportedFileError

MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024


def _parse_file_version(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("File version must be a non-negative decimal string.")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError("File version must be a non-negative decimal string.")


FileVersion = Annotated[
    int,
    BeforeValidator(_parse_file_version, json_schema_input_type=str),
    Field(ge=0),
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]


class ManagedWorkspacePath(BaseModel):
    """Normalized relative path inside one 致知 owner workspace."""

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Virtual file path must be relative and cannot contain '..'.")
        if str(path) in {"", "."}:
            raise ValueError("Virtual file path cannot be empty.")
        return str(path)


def ensure_supported_text_file(
    path: ManagedWorkspacePath,
    content: bytes,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> str:
    """Validate the path, size, and UTF-8 encoding of a managed text file."""

    del path
    if len(content) > max_bytes:
        raise UnsupportedFileError(f"Text file exceeds {max_bytes} bytes limit.")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFileError("Only UTF-8 text files are supported.") from exc
