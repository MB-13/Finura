"""Section-aware chunking of per-page Markdown.

Chunks follow the document's headings, aim for TARGET_MIN..TARGET_MAX tokens and never exceed
HARD_MAX. Each chunk remembers its heading breadcrumb (`section_path`) and page range.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from doctune.parsing.extract import Page

TARGET_MIN = 300
TARGET_MAX = 900
HARD_MAX = 1000
MIN_KEEP = 40

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


@dataclass
class Block:
    text: str
    section_path: str
    page: int | None
    tokens: int


@dataclass
class ChunkData:
    text: str
    section_path: str
    token_count: int
    page_start: int | None
    page_end: int | None


def _clean_heading(text: str) -> str:
    return re.sub(r"[*_`]+", "", text).strip()


def to_blocks(pages: list[Page]) -> list[Block]:
    """Split pages into paragraphs, tracking the heading stack as the breadcrumb."""
    stack: list[tuple[int, str]] = []
    blocks: list[Block] = []
    for page in pages:
        para: list[str] = []

        def flush(para: list[str] = para, page: Page = page) -> None:
            text = "\n".join(para).strip()
            para.clear()
            if text:
                path = " > ".join(t for _, t in stack)
                blocks.append(Block(text, path, page.number, count_tokens(text)))

        for line in page.markdown.splitlines():
            m = HEADING_RE.match(line.strip())
            if m:
                flush()
                level, title = len(m.group(1)), _clean_heading(m.group(2))
                if not title:
                    continue
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                para.append(f"{m.group(1)} {title}")
                flush()
            elif not line.strip():
                flush()
            else:
                para.append(line.rstrip())
        flush()
    return blocks


def _split_large(block: Block) -> list[Block]:
    """Split an oversized paragraph on sentences, then hard-split by tokens if needed."""
    pieces: list[Block] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in SENTENCE_RE.split(block.text):
        t = count_tokens(sentence)
        if t > HARD_MAX:
            if current:
                pieces.append(Block(" ".join(current), block.section_path, block.page, current_tokens))
                current, current_tokens = [], 0
            tokens = _encoding().encode(sentence, disallowed_special=())
            for i in range(0, len(tokens), TARGET_MAX):
                piece = _encoding().decode(tokens[i : i + TARGET_MAX])
                pieces.append(Block(piece, block.section_path, block.page, count_tokens(piece)))
            continue
        if current and current_tokens + t > TARGET_MAX:
            pieces.append(Block(" ".join(current), block.section_path, block.page, current_tokens))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += t
    if current:
        pieces.append(Block(" ".join(current), block.section_path, block.page, current_tokens))
    return pieces


def _merge(blocks: list[Block]) -> ChunkData:
    text = "\n\n".join(b.text for b in blocks)
    pages = [b.page for b in blocks if b.page is not None]
    return ChunkData(
        text=text,
        section_path=blocks[0].section_path,
        token_count=count_tokens(text),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
    )


def chunk_pages(pages: list[Page]) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    current: list[Block] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append(_merge(current))
        current, current_tokens = [], 0

    for block in to_blocks(pages):
        if block.tokens > HARD_MAX:
            flush()
            chunks.extend(_merge([piece]) for piece in _split_large(block))
            continue
        new_section = bool(current) and block.section_path != current[-1].section_path
        if current and (current_tokens + block.tokens > TARGET_MAX or (new_section and current_tokens >= TARGET_MIN)):
            flush()
        current.append(block)
        current_tokens += block.tokens
    flush()

    kept = [c for c in chunks if c.token_count >= MIN_KEEP]
    return kept or chunks
