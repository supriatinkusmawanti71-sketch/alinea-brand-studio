from uuid import uuid4

import pytest

from backend.infrastructure.storage import (
    InvalidArtifactReference,
    build_artifact_object_key,
    build_prefixed_artifact_object_key,
    build_temporary_artifact_prefix,
    sanitize_storage_filename,
    sanitize_storage_prefix,
    sanitize_storage_segment,
)


def test_build_artifact_object_key_matches_frontend_asset_contract() -> None:
    artifact_id = str(uuid4())

    result = build_artifact_object_key(
        project_id="project alpha",
        stage="LOGO",
        artifact_id=artifact_id,
        filename="../concept #1.png",
    )

    assert result == f"artifacts/project-alpha/logo/{artifact_id}/concept-1.png"


def test_build_prefixed_artifact_object_key_sanitizes_export_target() -> None:
    artifact_id = str(uuid4())

    result = build_prefixed_artifact_object_key(
        prefix="../tmp//exports/",
        artifact_id=artifact_id,
        filename="../My Export?.zip",
    )

    assert result == f"tmp/exports/{artifact_id}/My-Export.zip"


def test_build_prefixed_artifact_object_key_uses_fallback_filename() -> None:
    artifact_id = str(uuid4())

    result = build_prefixed_artifact_object_key(
        prefix="exports",
        artifact_id=artifact_id,
        filename="???",
        fallback_filename="brand-export.pdf",
    )

    assert result == f"exports/{artifact_id}/brand-export.pdf"


def test_build_temporary_artifact_prefix_returns_cleanup_safe_prefix() -> None:
    result = build_temporary_artifact_prefix(project_id="Project 1", scope="LOGO")

    assert result == "tmp/Project-1/logo/"


@pytest.mark.parametrize(
    "builder",
    [
        lambda: build_artifact_object_key(
            project_id="project-1",
            stage="logo",
            artifact_id="not-a-uuid",
            filename="logo.png",
        ),
        lambda: build_prefixed_artifact_object_key(
            prefix="exports",
            artifact_id="not-a-uuid",
            filename="deck.pdf",
        ),
    ],
)
def test_object_key_builders_reject_invalid_artifact_ids(builder) -> None:
    with pytest.raises(InvalidArtifactReference):
        builder()


def test_storage_sanitizers_strip_unsafe_path_parts() -> None:
    assert sanitize_storage_prefix("../tmp//exports/") == "tmp/exports"
    assert sanitize_storage_filename("../../Logo Final?.png") == "Logo-Final.png"
    assert sanitize_storage_segment("../DIRECTIONS v1") == "DIRECTIONS-v1"
