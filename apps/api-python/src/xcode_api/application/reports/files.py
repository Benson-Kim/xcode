"""From a report document to the file the answer carries: the writer whose content type the
document names builds the bytes off the event loop; the name and type come from the document,
never from the request."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from ...domain.reports import ExportFile, ExportFormat, ReportDocument
from ..errors import IntegrityBug
from ..ports import ReportFileWriter


async def build_file(
    writers: Mapping[ExportFormat, ReportFileWriter], document: ReportDocument
) -> ExportFile:
    writer = next((w for w in writers.values() if w.content_type == document.content_type), None)
    if writer is None:
        raise IntegrityBug(f"no export writer for {document.content_type}")
    content = await asyncio.to_thread(writer.write, document)
    return ExportFile(
        content=content, content_type=document.content_type, file_name=document.file_name
    )
