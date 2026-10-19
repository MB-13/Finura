"""Test documents generated in code (no binary fixtures in the repo)."""

import io
import zipfile

import pymupdf

LOREM = (
    "DocTune turns your documents into training data. Each section explains one feature in detail, "
    "with enough text to form realistic chunks for the chunker under test. "
)


def pdf_with_headings(sections: int = 3, paragraphs: int = 4) -> bytes:
    doc = pymupdf.open()
    for s in range(sections):
        page = doc.new_page()
        y = 72
        page.insert_text((72, y), f"Section {s + 1}", fontsize=22)
        y += 40
        for p in range(paragraphs):
            text = f"Paragraph {p + 1} of section {s + 1}. " + LOREM * 2
            rect = pymupdf.Rect(72, y, 540, y + 120)
            page.insert_textbox(rect, text, fontsize=10)
            y += 130
    out = doc.tobytes()
    doc.close()
    return out


def scanned_pdf(text: str = "Scanned invoice number 4521 total due 300 dollars") -> bytes:
    """A PDF whose only page is an image of text (needs OCR)."""
    src = pymupdf.open()
    page = src.new_page(width=600, height=200)
    page.insert_text((20, 100), text, fontsize=24)
    pix = page.get_pixmap(dpi=200)
    src.close()
    doc = pymupdf.open()
    img_page = doc.new_page(width=600, height=200)
    img_page.insert_image(img_page.rect, stream=pix.tobytes("png"))
    out = doc.tobytes()
    doc.close()
    return out


def encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    out = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
    doc.close()
    return out


def blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    out = doc.tobytes()
    doc.close()
    return out


def docx_with_headings() -> bytes:
    styles = (
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
        "</w:styles>"
    )

    def para(text: str, style: str | None = None) -> str:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"

    body = "".join(
        [
            para("User Guide", "Heading1"),
            para("Welcome to the guide. " + LOREM),
            para("Installation", "Heading2"),
            para("Install the app from the store. " + LOREM),
        ]
    )
    document = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    doc_rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return buf.getvalue()


def markdown_doc() -> bytes:
    return (
        "# Handbook\n\nIntro paragraph. " + LOREM + "\n\n## Leave policy\n\nYou get 20 days. " + LOREM + "\n"
    ).encode()
