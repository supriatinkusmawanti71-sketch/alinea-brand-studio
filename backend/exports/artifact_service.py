from __future__ import annotations

from backend.exports.models import (
    ExportArtifactTarget,
    ExportRequest,
    StoredExportArtifact,
)
from backend.exports.service import ExportRenderer
from backend.infrastructure.storage import (
    ArtifactReference,
    ArtifactStorage,
    ArtifactUpload,
    build_prefixed_artifact_object_key,
)


class ExportArtifactService:
    def __init__(
        self,
        *,
        storage: ArtifactStorage,
        renderer: ExportRenderer | None = None,
    ) -> None:
        self._storage = storage
        self._renderer = renderer or ExportRenderer()

    def render_and_store(
        self,
        request: ExportRequest,
        target: ExportArtifactTarget,
    ) -> StoredExportArtifact:
        export = self._renderer.render(request)
        object_key = build_prefixed_artifact_object_key(
            prefix=target.object_key_prefix,
            artifact_id=target.artifact_id,
            filename=export.filename,
            fallback_filename=f"brand-export.{export.format.value}",
        )
        reference = ArtifactReference(
            artifact_id=target.artifact_id,
            bucket=target.bucket,
            object_key=object_key,
            filename=export.filename,
            content_type=export.content_type,
        )
        stored = self._storage.put_artifact(
            ArtifactUpload(
                reference=reference,
                body=export.body,
                cache_control=target.cache_control,
            )
        )

        return StoredExportArtifact(
            export_id=export.export_id,
            artifact_id=target.artifact_id,
            format=export.format,
            filename=export.filename,
            content_type=export.content_type,
            byte_size=len(export.body),
            bucket=stored.bucket,
            object_key=stored.object_key,
            etag=stored.etag,
            version_id=stored.version_id,
        )
