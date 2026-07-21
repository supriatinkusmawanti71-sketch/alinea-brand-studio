from dataclasses import dataclass, field
from enum import StrEnum


class ExportFormat(StrEnum):
    PDF = "pdf"
    PPTX = "pptx"
    ZIP = "zip"


@dataclass(frozen=True, slots=True)
class ExportSection:
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class ExportAsset:
    path: str
    body: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class ExportDocument:
    title: str
    sections: tuple[ExportSection, ...] = ()
    assets: tuple[ExportAsset, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExportRequest:
    export_id: str
    format: ExportFormat
    document: ExportDocument
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    export_id: str
    format: ExportFormat
    filename: str
    content_type: str
    body: bytes


@dataclass(frozen=True, slots=True)
class ExportArtifactTarget:
    artifact_id: str
    bucket: str
    object_key_prefix: str = "exports"
    cache_control: str | None = "private, max-age=0, no-store"


@dataclass(frozen=True, slots=True)
class StoredExportArtifact:
    export_id: str
    artifact_id: str
    format: ExportFormat
    filename: str
    content_type: str
    byte_size: int
    bucket: str
    object_key: str
    etag: str | None
    version_id: str | None
