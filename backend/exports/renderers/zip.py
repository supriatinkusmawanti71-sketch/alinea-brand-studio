import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from backend.exports.models import ExportRequest


def render_zip(request: ExportRequest) -> bytes:
    output = BytesIO()
    document = request.document

    manifest = {
        "export_id": request.export_id,
        "format": request.format.value,
        "title": document.title,
        "metadata": document.metadata,
        "sections": [
            {
                "title": section.title,
                "body": section.body,
            }
            for section in document.sections
        ],
        "assets": [
            {
                "path": asset.path,
                "content_type": asset.content_type,
                "size": len(asset.body),
            }
            for asset in document.assets
        ],
    }

    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr("content.txt", _render_plain_text(request))
        for asset in document.assets:
            archive.writestr(_safe_asset_path(asset.path), asset.body)

    return output.getvalue()


def _render_plain_text(request: ExportRequest) -> str:
    lines = [request.document.title, ""]
    for section in request.document.sections:
        lines.extend([section.title, section.body, ""])
    return "\n".join(lines)


def _safe_asset_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "assets/" + "/".join(parts or ["asset.bin"])
