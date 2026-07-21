from uuid import uuid4

from backend.exports import (
    ExportArtifactService,
    ExportArtifactTarget,
    ExportDocument,
    ExportFormat,
    ExportRequest,
    ExportSection,
)
from backend.infrastructure.storage import ArtifactUpload, StoredArtifact


def test_render_and_store_uploads_export_body_to_artifact_storage() -> None:
    artifact_id = str(uuid4())
    storage = RecordingStorage()
    service = ExportArtifactService(storage=storage)

    result = service.render_and_store(
        ExportRequest(
            export_id="export-1",
            format=ExportFormat.PDF,
            document=_document(),
        ),
        ExportArtifactTarget(
            artifact_id=artifact_id,
            bucket="brand-studio",
            object_key_prefix="exports/project-1",
        ),
    )

    assert result.export_id == "export-1"
    assert result.artifact_id == artifact_id
    assert result.format == ExportFormat.PDF
    assert result.filename == "aline-brand.pdf"
    assert result.content_type == "application/pdf"
    assert result.byte_size == len(storage.upload.body)
    assert result.bucket == "brand-studio"
    assert result.object_key == f"exports/project-1/{artifact_id}/aline-brand.pdf"
    assert result.etag == '"etag"'
    assert storage.upload.reference.artifact_id == artifact_id
    assert storage.upload.reference.content_type == "application/pdf"
    assert storage.upload.cache_control == "private, max-age=0, no-store"
    assert bytes(storage.upload.body).startswith(b"%PDF-1.4")


def test_render_and_store_sanitizes_prefix_and_custom_filename() -> None:
    artifact_id = str(uuid4())
    storage = RecordingStorage()
    service = ExportArtifactService(storage=storage)

    result = service.render_and_store(
        ExportRequest(
            export_id="export-1",
            format=ExportFormat.ZIP,
            document=_document(),
            filename="../My Export?.zip",
        ),
        ExportArtifactTarget(
            artifact_id=artifact_id,
            bucket="brand-studio",
            object_key_prefix="../tmp//exports/",
            cache_control=None,
        ),
    )

    assert result.filename == "../My Export?.zip"
    assert result.object_key == f"tmp/exports/{artifact_id}/My-Export.zip"
    assert storage.upload.reference.filename == "../My Export?.zip"
    assert storage.upload.cache_control is None


class RecordingStorage:
    def __init__(self) -> None:
        self.upload: ArtifactUpload | None = None

    def put_artifact(self, upload: ArtifactUpload) -> StoredArtifact:
        self.upload = upload
        return StoredArtifact(
            artifact_id=upload.reference.artifact_id,
            bucket=upload.reference.bucket,
            object_key=upload.reference.object_key,
            etag='"etag"',
            version_id=None,
        )


def _document() -> ExportDocument:
    return ExportDocument(
        title="Aline Brand",
        sections=(
            ExportSection(
                title="Brand direction",
                body="Calm AI workbench for coordinated brand agents.",
            ),
        ),
    )
