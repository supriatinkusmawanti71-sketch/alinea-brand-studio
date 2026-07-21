from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.stub import Stubber

from backend.infrastructure.storage import (
    ArtifactNotFound,
    ArtifactReference,
    ArtifactUpload,
    InvalidArtifactReference,
    S3ArtifactStorage,
)


def test_create_download_url_returns_short_lived_get_url() -> None:
    reference = _artifact_reference()
    storage = S3ArtifactStorage(
        endpoint_url="http://minio.test",
        access_key="test",
        secret_key="test",
        region_name="us-east-1",
    )

    result = storage.create_download_url(reference)
    parsed = urlparse(result.url)
    query = parse_qs(parsed.query)

    assert result.artifact_id == reference.artifact_id
    assert result.method == "GET"
    assert result.expires_in_seconds == 900
    assert result.expires_at > datetime.now(UTC)
    assert parsed.path.endswith(f"/{reference.bucket}/{reference.object_key}")
    assert query["X-Amz-Expires"] == ["900"]
    assert "response-content-disposition" in query
    assert query["response-content-type"] == ["image/png"]


def test_put_artifact_uploads_body_and_returns_storage_result() -> None:
    reference = _artifact_reference()
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )

    with Stubber(client) as stubber:
        stubber.add_response(
            "put_object",
            {"ETag": '"abc123"', "VersionId": "version-1"},
            {
                "Bucket": reference.bucket,
                "Key": reference.object_key,
                "Body": b"png bytes",
                "ContentType": "image/png",
                "CacheControl": "max-age=60",
            },
        )

        result = storage.put_artifact(
            ArtifactUpload(
                reference=reference,
                body=b"png bytes",
                cache_control="max-age=60",
            )
        )

    assert result.artifact_id == reference.artifact_id
    assert result.bucket == reference.bucket
    assert result.object_key == reference.object_key
    assert result.etag == '"abc123"'
    assert result.version_id == "version-1"


def test_ensure_artifact_exists_returns_s3_metadata() -> None:
    reference = _artifact_reference()
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )
    last_modified = datetime(2026, 1, 1, tzinfo=UTC)

    with Stubber(client) as stubber:
        stubber.add_response(
            "head_object",
            {
                "ContentLength": 42,
                "ContentType": "image/png",
                "ETag": '"abc123"',
                "LastModified": last_modified,
            },
            {"Bucket": reference.bucket, "Key": reference.object_key},
        )

        metadata = storage.ensure_artifact_exists(reference)

    assert metadata.artifact_id == reference.artifact_id
    assert metadata.content_length == 42
    assert metadata.content_type == "image/png"
    assert metadata.etag == '"abc123"'
    assert metadata.last_modified == last_modified


def test_ensure_artifact_exists_maps_missing_objects() -> None:
    reference = _artifact_reference()
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )

    with Stubber(client) as stubber:
        stubber.add_client_error(
            "head_object",
            service_error_code="404",
            http_status_code=404,
            expected_params={"Bucket": reference.bucket, "Key": reference.object_key},
        )

        with pytest.raises(ArtifactNotFound):
            storage.ensure_artifact_exists(reference)


def test_delete_artifact_deletes_single_object() -> None:
    reference = _artifact_reference()
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )

    with Stubber(client) as stubber:
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": reference.bucket, "Key": reference.object_key},
        )

        storage.delete_artifact(reference)


def test_delete_artifacts_by_prefix_deletes_matching_temporary_objects() -> None:
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )
    bucket = "brand-studio"
    prefix = "tmp/project-1/"
    old_time = datetime(2026, 1, 1, tzinfo=UTC)
    cutoff = datetime(2026, 1, 2, tzinfo=UTC)

    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {
                "IsTruncated": False,
                "Name": bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
                "KeyCount": 2,
                "Contents": [
                    {"Key": f"{prefix}a.png", "LastModified": old_time},
                    {"Key": f"{prefix}b.png", "LastModified": old_time},
                ],
            },
            {"Bucket": bucket, "Prefix": prefix},
        )
        stubber.add_response(
            "delete_objects",
            {},
            {
                "Bucket": bucket,
                "Delete": {
                    "Objects": [
                        {"Key": f"{prefix}a.png"},
                        {"Key": f"{prefix}b.png"},
                    ],
                    "Quiet": True,
                },
            },
        )

        result = storage.delete_artifacts_by_prefix(
            bucket=bucket,
            prefix=prefix,
            older_than=cutoff,
        )

    assert result.bucket == bucket
    assert result.prefix == prefix
    assert result.scanned_count == 2
    assert result.deleted_count == 2
    assert result.failed_keys == ()


def test_delete_artifacts_by_prefix_skips_newer_objects() -> None:
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )
    bucket = "brand-studio"
    prefix = "tmp/project-1/"
    old_time = datetime(2026, 1, 1, tzinfo=UTC)
    new_time = datetime(2026, 1, 3, tzinfo=UTC)
    cutoff = datetime(2026, 1, 2, tzinfo=UTC)

    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {
                "IsTruncated": False,
                "Name": bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
                "KeyCount": 2,
                "Contents": [
                    {"Key": f"{prefix}old.png", "LastModified": old_time},
                    {"Key": f"{prefix}new.png", "LastModified": new_time},
                ],
            },
            {"Bucket": bucket, "Prefix": prefix},
        )
        stubber.add_response(
            "delete_objects",
            {},
            {
                "Bucket": bucket,
                "Delete": {
                    "Objects": [
                        {"Key": f"{prefix}old.png"},
                    ],
                    "Quiet": True,
                },
            },
        )

        result = storage.delete_artifacts_by_prefix(
            bucket=bucket,
            prefix=prefix,
            older_than=cutoff,
        )

    assert result.scanned_count == 2
    assert result.deleted_count == 1


def test_delete_artifacts_by_prefix_reports_failed_keys() -> None:
    client = _s3_client()
    storage = S3ArtifactStorage(
        endpoint_url=None,
        access_key="unused",
        secret_key="unused",
        region_name="us-east-1",
        client=client,
    )
    bucket = "brand-studio"
    prefix = "tmp/project-1/"

    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {
                "IsTruncated": False,
                "Name": bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
                "KeyCount": 1,
                "Contents": [
                    {"Key": f"{prefix}stuck.png", "LastModified": datetime(2026, 1, 1, tzinfo=UTC)},
                ],
            },
            {"Bucket": bucket, "Prefix": prefix},
        )
        stubber.add_response(
            "delete_objects",
            {
                "Errors": [
                    {
                        "Key": f"{prefix}stuck.png",
                        "Code": "InternalError",
                        "Message": "failed",
                    }
                ]
            },
            {
                "Bucket": bucket,
                "Delete": {
                    "Objects": [
                        {"Key": f"{prefix}stuck.png"},
                    ],
                    "Quiet": True,
                },
            },
        )

        result = storage.delete_artifacts_by_prefix(bucket=bucket, prefix=prefix)

    assert result.scanned_count == 1
    assert result.deleted_count == 0
    assert result.failed_keys == (f"{prefix}stuck.png",)


@pytest.mark.parametrize(
    ("artifact_id", "object_key", "ttl"),
    [
        ("not-a-uuid", "artifacts/project/logo.png", 900),
        (str(uuid4()), "../logo.png", 900),
        (str(uuid4()), "artifacts//logo.png", 900),
        (str(uuid4()), "artifacts/project/logo.png", 59),
        (str(uuid4()), "artifacts/project/logo.png", 3601),
    ],
)
def test_create_download_url_rejects_unsafe_references(
    artifact_id: str,
    object_key: str,
    ttl: int,
) -> None:
    reference = ArtifactReference(
        artifact_id=artifact_id,
        bucket="brand-studio",
        object_key=object_key,
    )
    storage = S3ArtifactStorage(
        endpoint_url="http://minio.test",
        access_key="test",
        secret_key="test",
        region_name="us-east-1",
    )

    with pytest.raises(InvalidArtifactReference):
        storage.create_download_url(reference, expires_in_seconds=ttl)


@pytest.mark.parametrize(
    ("prefix", "batch_size"),
    [
        ("tmp/project-1", 1000),
        ("../tmp/", 1000),
        ("tmp//project-1/", 1000),
        ("tmp/project-1/", 0),
        ("tmp/project-1/", 1001),
    ],
)
def test_delete_artifacts_by_prefix_rejects_unsafe_cleanup_input(
    prefix: str,
    batch_size: int,
) -> None:
    storage = S3ArtifactStorage(
        endpoint_url="http://minio.test",
        access_key="test",
        secret_key="test",
        region_name="us-east-1",
    )

    with pytest.raises(InvalidArtifactReference):
        storage.delete_artifacts_by_prefix(
            bucket="brand-studio",
            prefix=prefix,
            batch_size=batch_size,
        )


def _artifact_reference() -> ArtifactReference:
    return ArtifactReference(
        artifact_id=str(uuid4()),
        bucket="brand-studio",
        object_key="artifacts/project/logo.png",
        filename="logo.png",
        content_type="image/png",
    )


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url="http://minio.test",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
