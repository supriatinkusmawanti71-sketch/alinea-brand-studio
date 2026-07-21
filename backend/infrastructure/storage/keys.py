from __future__ import annotations

import re
from uuid import UUID

from backend.infrastructure.storage.errors import InvalidArtifactReference

_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_SEGMENT_LENGTH = 180


def build_artifact_object_key(
    *,
    project_id: str,
    stage: str,
    artifact_id: str,
    filename: str | None = None,
    root_prefix: str = "artifacts",
) -> str:
    """Build a stable key for files that should be addressable from UI asset ids."""

    normalized_artifact_id = normalize_artifact_id(artifact_id)
    safe_root = sanitize_storage_segment(root_prefix, fallback="artifacts")
    safe_project = sanitize_storage_segment(project_id, fallback="project")
    safe_stage = sanitize_storage_segment(stage.lower(), fallback="stage")
    safe_filename = sanitize_storage_filename(filename, fallback=normalized_artifact_id)

    return "/".join(
        (
            safe_root,
            safe_project,
            safe_stage,
            normalized_artifact_id,
            safe_filename,
        )
    )


def build_prefixed_artifact_object_key(
    *,
    prefix: str,
    artifact_id: str,
    filename: str | None,
    fallback_filename: str = "artifact",
) -> str:
    normalized_artifact_id = normalize_artifact_id(artifact_id)
    safe_prefix = sanitize_storage_prefix(prefix, fallback="artifacts")
    safe_filename = sanitize_storage_filename(filename, fallback=fallback_filename)

    return f"{safe_prefix}/{normalized_artifact_id}/{safe_filename}"


def build_temporary_artifact_prefix(
    *,
    project_id: str,
    scope: str | None = None,
    root_prefix: str = "tmp",
) -> str:
    safe_root = sanitize_storage_segment(root_prefix, fallback="tmp")
    safe_project = sanitize_storage_segment(project_id, fallback="project")
    segments = [safe_root, safe_project]

    if scope:
        segments.append(sanitize_storage_segment(scope.lower(), fallback="scope"))

    return "/".join(segments) + "/"


def normalize_artifact_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise InvalidArtifactReference("artifact_id must be a UUID string") from exc


def sanitize_storage_prefix(value: str, *, fallback: str = "artifacts") -> str:
    segments = []
    for raw_part in value.replace("\\", "/").split("/"):
        if raw_part in {"", ".", ".."}:
            continue
        safe_part = sanitize_storage_segment(raw_part, fallback="")
        if safe_part:
            segments.append(safe_part)

    if segments:
        return "/".join(segments)
    return sanitize_storage_segment(fallback, fallback="artifacts")


def sanitize_storage_filename(
    value: str | None,
    *,
    fallback: str = "artifact",
    max_length: int = _MAX_SEGMENT_LENGTH,
) -> str:
    filename = (value or "").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    safe = _SAFE_SEGMENT_RE.sub("-", filename).strip(".-")
    safe = re.sub(r"-+(\.[A-Za-z0-9]+)$", r"\1", safe)

    if not safe:
        safe = sanitize_storage_segment(fallback, fallback="artifact", max_length=max_length)

    return safe[:max_length]


def sanitize_storage_segment(
    value: str | None,
    *,
    fallback: str = "item",
    max_length: int = _MAX_SEGMENT_LENGTH,
) -> str:
    raw = (value or "").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    safe = _SAFE_SEGMENT_RE.sub("-", raw).strip(".-")

    if not safe and fallback:
        safe = _SAFE_SEGMENT_RE.sub("-", fallback).strip(".-")

    return safe[:max_length]
