import json
from io import BytesIO
from zipfile import ZipFile

from backend.exports import (
    ExportAsset,
    ExportDocument,
    ExportFormat,
    ExportRenderer,
    ExportRequest,
    ExportSection,
)


def test_render_pdf_returns_pdf_bytes() -> None:
    result = ExportRenderer().render(_request(ExportFormat.PDF))

    assert result.filename == "aline-brand.pdf"
    assert result.content_type == "application/pdf"
    assert result.body.startswith(b"%PDF-1.4")
    assert b"Brand direction" in result.body
    assert b"%%EOF" in result.body


def test_render_pptx_returns_openxml_package() -> None:
    result = ExportRenderer().render(_request(ExportFormat.PPTX))

    assert result.filename == "aline-brand.pptx"
    assert result.content_type.endswith("presentationml.presentation")

    with ZipFile(BytesIO(result.body)) as archive:
        names = set(archive.namelist())
        slide_1 = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        slide_2 = archive.read("ppt/slides/slide2.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "ppt/presentation.xml" in names
    assert "ppt/slides/slide1.xml" in names
    assert "ppt/slides/slide2.xml" in names
    assert "Aline Brand" in slide_1
    assert "Brand direction" in slide_2


def test_render_zip_returns_manifest_content_and_assets() -> None:
    result = ExportRenderer().render(_request(ExportFormat.ZIP))

    assert result.filename == "aline-brand.zip"
    assert result.content_type == "application/zip"

    with ZipFile(BytesIO(result.body)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        content = archive.read("content.txt").decode("utf-8")
        asset_body = archive.read("assets/logo.png")

    assert manifest["export_id"] == "export-1"
    assert manifest["title"] == "Aline Brand"
    assert manifest["assets"] == [
        {
            "path": "logo.png",
            "content_type": "image/png",
            "size": 9,
        }
    ]
    assert "Brand direction" in content
    assert asset_body == b"png-bytes"


def test_custom_filename_is_preserved() -> None:
    request = ExportRequest(
        export_id="export-1",
        format=ExportFormat.ZIP,
        document=_document(),
        filename="custom-export.zip",
    )

    result = ExportRenderer().render(request)

    assert result.filename == "custom-export.zip"


def _request(export_format: ExportFormat) -> ExportRequest:
    return ExportRequest(
        export_id="export-1",
        format=export_format,
        document=_document(),
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
        assets=(
            ExportAsset(
                path="logo.png",
                body=b"png-bytes",
                content_type="image/png",
            ),
        ),
        metadata={"project_id": "project-1"},
    )
