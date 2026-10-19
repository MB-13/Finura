import pytest
from fixtures import (
    LOREM,
    blank_pdf,
    docx_with_headings,
    encrypted_pdf,
    markdown_doc,
    pdf_with_headings,
    scanned_pdf,
)

from doctune.parsing.chunker import HARD_MAX, MIN_KEEP, TARGET_MAX, chunk_pages, count_tokens, to_blocks
from doctune.parsing.extract import Page, ParseError, extract, kind_for_filename, sniff


def test_kind_for_filename() -> None:
    assert kind_for_filename("Guide.PDF") == "pdf"
    assert kind_for_filename("notes.markdown") == "md"
    assert kind_for_filename("a.docx") == "docx"
    assert kind_for_filename("evil.exe") is None
    assert kind_for_filename("noext") is None


def test_sniff_checks_real_type() -> None:
    assert sniff(pdf_with_headings(1, 1)[:8192], "pdf")
    assert not sniff(b"<html>not a pdf", "pdf")
    assert sniff(docx_with_headings()[:8192], "docx")
    assert not sniff(b"%PDF-1.7", "docx")
    assert sniff(b"plain text", "txt")
    assert not sniff(b"\x00\x01\x02binary", "txt")


def test_pdf_extracts_pages_and_headings() -> None:
    result = extract(pdf_with_headings(sections=3), "pdf")
    assert result.page_count == 3
    assert result.ocr_pages == 0
    assert "Section 2" in result.pages[1].markdown


def test_scanned_pdf_is_ocrd() -> None:
    result = extract(scanned_pdf(), "pdf")
    assert result.ocr_pages == 1
    assert "4521" in result.pages[0].markdown


def test_encrypted_pdf_has_clear_error() -> None:
    with pytest.raises(ParseError, match="password"):
        extract(encrypted_pdf(), "pdf")


def test_blank_pdf_has_no_text() -> None:
    with pytest.raises(ParseError, match="No readable text"):
        extract(blank_pdf(), "pdf")


def test_garbage_pdf() -> None:
    with pytest.raises(ParseError):
        extract(b"%PDF-1.7 this is not really a pdf", "pdf")


def test_docx_headings_become_markdown() -> None:
    result = extract(docx_with_headings(), "docx")
    md = result.pages[0].markdown
    assert "# User Guide" in md
    assert "## Installation" in md


def test_docx_rejects_non_word_zip() -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ParseError, match="valid Word"):
        extract(buf.getvalue(), "docx")


def test_text_encodings() -> None:
    assert "café" in extract("café menu".encode("utf-16"), "txt").pages[0].markdown
    assert "Handbook" in extract(markdown_doc(), "md").pages[0].markdown


def test_section_paths_follow_heading_stack() -> None:
    pages = [Page(1, "# Guide\n\nIntro.\n\n## Setup\n\nInstall it.\n\n### Linux\n\nUse apt.\n\n## Usage\n\nRun it.")]
    paths = [b.section_path for b in to_blocks(pages)]
    assert "Guide > Setup > Linux" in paths
    assert paths[-1] == "Guide > Usage"


def test_chunks_respect_size_limits_and_keep_pages() -> None:
    chunks = chunk_pages(extract(pdf_with_headings(sections=5, paragraphs=4), "pdf").pages)
    assert chunks
    for c in chunks:
        assert c.token_count <= HARD_MAX
        assert c.token_count >= MIN_KEEP
        assert c.page_start is not None and c.page_end is not None
        assert c.page_start <= c.page_end


def test_oversized_paragraph_is_split() -> None:
    huge = " ".join([LOREM] * 120)  # several thousand tokens, no headings
    chunks = chunk_pages([Page(1, huge)])
    assert len(chunks) > 1
    assert all(c.token_count <= HARD_MAX for c in chunks)


def test_small_sections_merge_into_one_chunk() -> None:
    md = "\n\n".join(f"## Topic {i}\n\n{LOREM}" for i in range(4))
    chunks = chunk_pages([Page(1, md)])
    assert len(chunks) == 1
    assert chunks[0].token_count <= TARGET_MAX


def test_repeated_headers_and_footers_are_removed() -> None:
    pages = [Page(i, f"ACME Confidential\n\n# Part {i}\n\n{LOREM}\n\nPage footer text") for i in range(1, 6)]
    doc = extract("\n".join(p.markdown for p in pages).encode(), "md")  # single page: nothing stripped
    assert "ACME Confidential" in doc.pages[0].markdown
    from doctune.parsing.extract import _strip_repeated_lines

    stripped = _strip_repeated_lines(pages)
    assert all("ACME Confidential" not in p.markdown for p in stripped)
    assert all("# Part" in p.markdown for p in stripped)


def test_count_tokens_handles_special_tokens() -> None:
    assert count_tokens("<|endoftext|> hello") > 0
