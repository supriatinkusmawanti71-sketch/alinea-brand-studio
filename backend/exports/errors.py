class ExportError(RuntimeError):
    """Base error for export rendering."""


class UnsupportedExportFormat(ExportError, ValueError):
    def __init__(self, export_format: str) -> None:
        super().__init__(f"unsupported export format: {export_format}")
