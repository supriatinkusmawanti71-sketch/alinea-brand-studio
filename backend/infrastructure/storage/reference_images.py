from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import boto3
import psycopg

_SUPPORTED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}


@dataclass(frozen=True)
class ReferenceImageLocation:
    bucket: str
    object_key: str
    mime_type: str


class ReferenceImageResolver:
    """Turn stored artifact ids into base64 data URIs for image-to-image calls.

    External image providers cannot reach the private object store, so the
    reference image is inlined into the request body instead of linked by URL.
    Providers call this synchronously from the Celery worker, hence the
    short-lived sync database connection instead of the shared async engine.
    """

    def __init__(
        self,
        *,
        database_conninfo: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        use_ssl: bool,
        s3_client: Any | None = None,
        locate_artifact: Callable[[str], ReferenceImageLocation | None] | None = None,
    ) -> None:
        self._database_conninfo = database_conninfo
        self._client = s3_client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            use_ssl=use_ssl,
        )
        self._locate_artifact = locate_artifact or self._locate_via_database
        self._cache: dict[str, str] = {}
        # Artifacts stored earlier in the SAME stage run are not committed to
        # the database yet (the run commits once at the end), so the writer
        # registers them here and lookups check this index first.
        self._local_index: dict[str, ReferenceImageLocation] = {}

    def register_stored_artifact(
        self,
        artifact_id: str,
        *,
        bucket: str,
        object_key: str,
        mime_type: str,
    ) -> None:
        self._local_index[artifact_id] = ReferenceImageLocation(
            bucket=bucket,
            object_key=object_key,
            mime_type=mime_type,
        )

    def __call__(self, artifact_id: str) -> str:
        cached = self._cache.get(artifact_id)
        if cached is not None:
            return cached
        location = self._local_index.get(artifact_id) or self._locate_artifact(artifact_id)
        if location is None:
            raise ValueError(f"Reference image artifact not found: {artifact_id}")
        if location.mime_type not in _SUPPORTED_MIME_TYPES:
            raise ValueError(
                f"Reference artifact {artifact_id} has unsupported MIME type: "
                f"{location.mime_type}"
            )
        stored_object = self._client.get_object(
            Bucket=location.bucket,
            Key=location.object_key,
        )
        content = stored_object["Body"].read()
        encoded = base64.b64encode(content).decode("ascii")
        data_uri = f"data:{location.mime_type};base64,{encoded}"
        self._cache[artifact_id] = data_uri
        return data_uri

    def _locate_via_database(self, artifact_id: str) -> ReferenceImageLocation | None:
        with psycopg.connect(self._database_conninfo) as connection:
            row = connection.execute(
                "SELECT bucket, object_key, mime_type FROM artifacts"
                " WHERE id = %s AND status = 'STORED'",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        return ReferenceImageLocation(bucket=row[0], object_key=row[1], mime_type=row[2])
