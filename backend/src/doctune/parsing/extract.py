"""Turn an uploaded file into per-page Markdown. Runs inside the `parse` worker only."""

import io
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from charset_normalizer import from_bytes

Kind = Literal["pdf", "docx", "txt", "md"]

MAX_PAGES = 500
OCR_MIN_CHARS = 50  # pages with less extracted text than this are OCR'd if they contain images
OCR_DPI = 200

CONTENT_TYPES: dict[Kind, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}


class ParseError(Exception):
    """A problem the user can act on; the message is shown in the UI."""


@dataclass
class Page:
    number: int | None
    markdown: str


@dataclass
class Extracted:
    pages: list[Page]
    page_count: int | None = None
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)


def kind_for_filename(filename: str) -> Kind | None:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "markdown":
        ext = "md"
    return ext if ext in CONTENT_TYPES else None


def sniff(head: bytes, kind: Kind) -> bool:
    """Check the file's real type from its first bytes (never trust the extension alone)."""
    if kind == "pdf":
        return head.lstrip()[:5] == b"%PDF-"
    if kind == "docx":
        # full check (word/document.xml inside the zip) happens at parse time with the whole file
        return head.startswith(b"PK\x03\x04")
    # text: no NUL bytes and decodable
    if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False
    return from_bytes(head).best() is not None or not head


def _decode(data: bytes) -> str:
    best = from_bytes(data).best()
    if best is None:
        raise ParseError("We couldn't read this text file's encoding.")
    return str(best)


def _strip_repeated_lines(pages: list[Page]) -> list[Page]:
    """Drop running headers/footers: short lines that repeat on more than half of the pages."""
    if len(pages) < 4:
        return pages
    counts: Counter[str] = Counter()
    for p in pages:
        counts.update({line.strip() for line in p.markdown.splitlines() if 0 < len(line.strip()) <= 80})
    repeated = {line for line, n in counts.items() if n > len(pages) / 2 and not line.startswith("#")}
    if not repeated:
        return pages
    return [
        Page(p.number, "\n".join(line for line in p.markdown.splitlines() if line.strip() not in repeated))
        for p in pages
    ]


def _ocr_page(page: "object", lang: str) -> str:
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=OCR_DPI)  # type: ignore[attr-defined]
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return str(pytesseract.image_to_string(image, lang=lang))


def extract_pdf(data: bytes, ocr_lang: str = "eng") -> Extracted:
    import pymupdf
    import pymupdf4llm

    try:
        doc: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise ParseError("This PDF looks damaged and couldn't be opened.") from exc
    with doc:
        if doc.needs_pass:
            raise ParseError("This PDF is password-protected. Remove the password and upload it again.")
        if doc.page_count == 0:
            raise ParseError("This PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise ParseError(f"This PDF has {doc.page_count} pages; the limit is {MAX_PAGES}.")
        chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
        pages: list[Page] = []
        ocr_pages = 0
        for i, item in enumerate(chunks):
            text = str(item.get("text", ""))
            # a page without a native text layer but with images is a scan: count it as OCR'd,
            # whether pymupdf4llm already OCR'd it or our fallback does
            if len(doc[i].get_text().strip()) < OCR_MIN_CHARS and doc[i].get_images():
                ocr_pages += 1
                if len(text.strip()) < OCR_MIN_CHARS:
                    ocred = _ocr_page(doc[i], ocr_lang).strip()
                    if len(ocred) > len(text.strip()):
                        text = ocred
            pages.append(Page(number=i + 1, markdown=text))
        return Extracted(pages=_strip_repeated_lines(pages), page_count=doc.page_count, ocr_pages=ocr_pages)


def extract_docx(data: bytes) -> Extracted:
    import mammoth
    from markdownify import markdownify

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "word/document.xml" not in z.namelist():
                raise ParseError("This file isn't a valid Word document.")
            # zip-bomb guard: refuse archives that expand to more than 200 MB
            if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:
                raise ParseError("This Word document is too large to process.")
    except zipfile.BadZipFile as exc:
        raise ParseError("This file isn't a valid Word document.") from exc
    result = mammoth.convert_to_html(io.BytesIO(data))
    markdown = markdownify(result.value, heading_style="ATX", strip=["img"])
    return Extracted(pages=[Page(number=None, markdown=markdown)])


def extract_text(data: bytes, kind: Kind) -> Extracted:
    text = _decode(data).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return Extracted(pages=[Page(number=None, markdown=text)])


def extract(data: bytes, kind: Kind, *, ocr_lang: str = "eng") -> Extracted:
    if kind == "pdf":
        result = extract_pdf(data, ocr_lang)
    elif kind == "docx":
        result = extract_docx(data)
    else:
        result = extract_text(data, kind)
    if not any(p.markdown.strip() for p in result.pages):
        raise ParseError("No readable text found in this file.")
    return result
