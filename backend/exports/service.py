from backend.exports.errors import UnsupportedExportFormat
from backend.exports.models import ExportFormat, ExportRequest, ExportResult
from backend.exports.renderers.pdf import render_pdf
from backend.exports.renderers.pptx import render_pptx
from backend.exports.renderers.zip import render_zip

_CONTENT_TYPES = {
    ExportFormat.PDF: "application/pdf",
    ExportFormat.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ExportFormat.ZIP: "application/zip",
}


class ExportRenderer:
    def render(self, request: ExportRequest) -> ExportResult:
        export_format = ExportFormat(request.format)
        filename = request.filename or _default_filename(request.document.title, export_format)

        if export_format == ExportFormat.PDF:
            body = render_pdf(request.document)
        elif export_format == ExportFormat.PPTX:
            body = render_pptx(request.document)
        elif export_format == ExportFormat.ZIP:
            body = render_zip(request)
        else:
            raise UnsupportedExportFormat(str(export_format))

        return ExportResult(
            export_id=request.export_id,
            format=export_format,
            filename=filename,
            content_type=_CONTENT_TYPES[export_format],
            body=body,
        )


def _default_filename(title: str, export_format: ExportFormat) -> str:
    slug = "-".join(_safe_filename_part(title).split())
    return f"{slug or 'brand-export'}.{export_format.value}"


def _safe_filename_part(value: str) -> str:
    return "".join(character if character.isalnum() else " " for character in value).strip().lower()
