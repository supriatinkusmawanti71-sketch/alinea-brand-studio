from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import boto3
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.ports import StoredArtifact
from backend.infrastructure.database.models import Artifact
from backend.providers.models.base import GeneratedImage

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class S3ArtifactWriter:
    """Store generated images privately and register their durable metadata."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        workspace_id: str,
        project_id: str,
        stage_run_id: str,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        use_ssl: bool,
        client: Any | None = None,
        on_stored: Callable[..., None] | None = None,
    ) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._project_id = project_id
        self._stage_run_id = stage_run_id
        self._bucket = bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            use_ssl=use_ssl,
        )
        self._pending: dict[UUID, Artifact] = {}
        # Callback letting the reference-image resolver see artifacts stored
        # in this run before the surrounding transaction commits.
        self._on_stored = on_stored

    def store_generated_image(
        self,
        *,
        request_id: str,
        image: GeneratedImage,
    ) -> StoredArtifact:
        if not image.content:
            raise ValueError("Generated image content must not be empty")
        if image.mime_type not in _EXTENSIONS:
            raise ValueError(f"Unsupported generated image MIME type: {image.mime_type}")

        artifact_id = uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    "generated-artifact",
                    self._project_id,
                    self._stage_run_id,
                    request_id,
                    image.provider_request_id,
                )
            ),
        )
        object_key = str(
            PurePosixPath(
                "projects",
                self._project_id,
                "stage-runs",
                self._stage_run_id,
                f"{artifact_id}{_EXTENSIONS[image.mime_type]}",
            )
        )
        digest = sha256(image.content).hexdigest()
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=image.content,
            ContentType=image.mime_type,
            Metadata={"sha256": digest},
        )
        artifact = Artifact(
            id=str(artifact_id),
            workspace_id=self._workspace_id,
            project_id=self._project_id,
            stage_run_id=self._stage_run_id,
            kind="GENERATED_IMAGE",
            storage_provider="S3",
            bucket=self._bucket,
            object_key=object_key,
            mime_type=image.mime_type,
            size_bytes=len(image.content),
            width=image.width,
            height=image.height,
            sha256=digest,
            status="STORED",
            metadata_json={
                "request_id": request_id,
                "provider": image.provider,
                "model": image.model,
                "provider_request_id": image.provider_request_id,
            },
        )
        self._session.add(artifact)
        self._pending[artifact_id] = artifact
        if self._on_stored is not None:
            self._on_stored(
                str(artifact_id),
                bucket=self._bucket,
                object_key=object_key,
                mime_type=image.mime_type,
            )
        return StoredArtifact(
            artifact_id=artifact_id,
            mime_type=image.mime_type,
            size_bytes=len(image.content),
        )

    def discard_temporary_artifacts(self, artifact_ids: list[UUID]) -> None:
        for artifact_id in artifact_ids:
            artifact = self._pending.get(artifact_id)
            if artifact is None or artifact.status == "DISCARDED":
                continue
            self._client.delete_object(Bucket=artifact.bucket, Key=artifact.object_key)
            artifact.status = "DISCARDED"
