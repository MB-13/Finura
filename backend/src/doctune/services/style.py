"""Style templates, validation warnings and immutable style snapshots."""

import hashlib
import json
import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.llm.prompts import StyleSpec
from doctune.models.generation import DatasetPair, PairOrigin, StyleConfig
from doctune.models.project import Project
from doctune.services import formats
from doctune.services.formats import DatasetFormat

Tone = Literal["neutral", "friendly", "formal", "casual", "technical", "enthusiastic"]
Length = Literal["short", "medium", "long"]
Format = Literal["plain", "bullets", "json", "markdown"]


class Example(BaseModel):
    input: str = Field(min_length=1, max_length=2000)
    output: str = Field(min_length=1, max_length=4000)


class StyleIn(BaseModel):
    template_key: str | None = None
    description: str = Field(min_length=10, max_length=2000)
    tone: Tone = "neutral"
    length: Length = "medium"
    format: Format = "plain"
    language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    examples: list[Example] = Field(min_length=1, max_length=5)
    system_prompt_in_data: bool = False
    # the shape of each training example; `format` above is the shape of each answer
    dataset_format: DatasetFormat = formats.DEFAULT_FORMAT


class Warning(BaseModel):
    code: str
    message: str


class StyleTemplate(BaseModel):
    key: str
    name: str
    description: str
    defaults: StyleIn


TEMPLATES: list[StyleTemplate] = [
    StyleTemplate(
        key="support_bot",
        name="Customer support bot",
        description="Friendly, short answers that solve the problem and offer more help.",
        defaults=StyleIn(
            description="A friendly support agent. Short sentences, solve the customer's problem step by step, "
            "and end by offering more help.",
            tone="friendly",
            length="short",
            format="plain",
            examples=[
                Example(
                    input="How do I reset my password?",
                    output="Happy to help! Go to Settings > Account, tap Reset password and follow the email "
                    "link. Anything else I can help with?",
                ),
                Example(
                    input="Can I change my plan later?",
                    output="Yes, anytime! Open Billing, pick a new plan and it applies right away. Anything "
                    "else I can help with?",
                ),
            ],
        ),
    ),
    StyleTemplate(
        key="tech_docs_assistant",
        name="Technical docs assistant",
        description="Precise, technical answers with steps and exact names.",
        defaults=StyleIn(
            description="A precise technical documentation assistant. Use exact names of settings, commands and "
            "files. Prefer numbered steps for procedures.",
            tone="technical",
            length="medium",
            format="markdown",
            examples=[
                Example(
                    input="How do I enable verbose logging?",
                    output="Set `LOG_LEVEL=debug` in your `.env` file, then restart the service:\n\n"
                    "1. Edit `.env`\n2. Run `systemctl restart app`",
                ),
                Example(
                    input="What does the timeout option control?",
                    output="`timeout` sets how long a request may run before it is cancelled, in seconds. "
                    "The default is `30`.",
                ),
            ],
        ),
    ),
    StyleTemplate(
        key="json_extractor",
        name="JSON extractor",
        description="Answers are JSON objects with the requested fields.",
        defaults=StyleIn(
            description="Extract the requested facts and reply only with a JSON object; use null when the "
            "information is missing.",
            tone="neutral",
            length="short",
            format="json",
            examples=[
                Example(
                    input="Who is the author and when was it published?",
                    output='{"author": "Jane Doe", "published": "2024-05-01"}',
                ),
                Example(input="What is the price and currency?", output='{"price": 49, "currency": "USD"}'),
            ],
        ),
    ),
    StyleTemplate(
        key="faq_bot",
        name="FAQ answers",
        description="Clear, neutral answers for an FAQ page.",
        defaults=StyleIn(
            description="Answer like a well-written FAQ: one clear direct answer first, then one sentence of "
            "useful detail.",
            tone="neutral",
            length="short",
            format="plain",
            examples=[
                Example(
                    input="Is there a free trial?",
                    output="Yes. Every account gets 14 days free, and no card is needed to start.",
                ),
                Example(
                    input="Where is my data stored?",
                    output="In the EU. All data is encrypted at rest and in transit.",
                ),
            ],
        ),
    ),
    StyleTemplate(
        key="tutor",
        name="Patient tutor",
        description="Explains concepts simply with an example.",
        defaults=StyleIn(
            description="A patient tutor. Explain the idea in simple words, then give one short concrete example.",
            tone="friendly",
            length="medium",
            format="plain",
            examples=[
                Example(
                    input="What is compound interest?",
                    output="It's interest you earn on your interest. For example, 100 at 10% becomes 110 "
                    "after a year, then 121 the next year, because the 10 you earned also earns interest.",
                ),
            ],
        ),
    ),
]
TEMPLATE_BY_KEY = {t.key: t for t in TEMPLATES}


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def warnings_for(style: StyleIn) -> list[Warning]:
    out: list[Warning] = []
    if len(style.examples) == 1:
        out.append(
            Warning(
                code="single_example",
                message="Add 2–5 examples. With one example the model may copy it too closely.",
            )
        )
    if len(style.description) < 40:
        out.append(
            Warning(
                code="description_short",
                message="Describe the style in a bit more detail (who is answering, how, for whom).",
            )
        )
    outputs = [e.output for e in style.examples]
    if style.format == "json" and not all(_is_json(o) for o in outputs):
        out.append(
            Warning(
                code="examples_inconsistent",
                message="Format is JSON but some example outputs aren't valid JSON.",
            )
        )
    elif style.format == "bullets" and not all(re.search(r"^\s*[-*•]", o, re.M) for o in outputs):
        out.append(
            Warning(
                code="examples_inconsistent",
                message="Format is bullets but some examples have no bullet points.",
            )
        )
    elif len(outputs) > 1:
        lengths = [_words(o) for o in outputs]
        if min(lengths) and max(lengths) / min(lengths) > 4:
            out.append(
                Warning(
                    code="examples_inconsistent",
                    message="Your examples have very different lengths; the model may be inconsistent.",
                )
            )
    return out


def content_hash(style: StyleIn) -> str:
    # leave the default format out so styles saved before dataset formats keep their hash
    exclude = {"template_key"} | ({"dataset_format"} if style.dataset_format == formats.DEFAULT_FORMAT else set())
    payload = style.model_dump(exclude=exclude)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def save(db: AsyncSession, project: Project, style: StyleIn) -> StyleConfig:
    digest = content_hash(style)
    current = await db.get(StyleConfig, project.style_id) if project.style_id else None
    if current is not None and current.content_hash == digest:
        return current
    row = StyleConfig(
        project_id=project.id,
        template_key=style.template_key,
        description=style.description.strip(),
        tone=style.tone,
        length=style.length,
        format=style.format,
        language=style.language,
        examples=[e.model_dump() for e in style.examples],
        system_prompt_in_data=style.system_prompt_in_data,
        dataset_format=style.dataset_format,
        content_hash=digest,
    )
    db.add(row)
    await db.flush()
    project.style_id = row.id
    await _reshape_user_pairs(db, project, style.dataset_format)
    await db.commit()
    await db.refresh(row)
    return row


async def _reshape_user_pairs(db: AsyncSession, project: Project, to: str) -> None:
    """Pairs the user added survive a restyle; give them the new dataset format, or set aside the ones that can't
    take it without losing turns (a longer conversation going to a single-turn format)."""
    # set-aside pairs whose format matches again come back
    await db.execute(
        update(DatasetPair)
        .where(
            DatasetPair.project_id == project.id,
            DatasetPair.origin == PairOrigin.user_added,
            DatasetPair.dataset_format == to,
            DatasetPair.dropped_reason == "format_changed",
        )
        .values(kept=True, dropped_reason=None)
    )
    pairs = (
        await db.scalars(
            select(DatasetPair).where(
                DatasetPair.project_id == project.id,
                DatasetPair.origin == PairOrigin.user_added,
                DatasetPair.dataset_format != to,
            )
        )
    ).all()
    for pair in pairs:
        rec = formats.convert(pair.dataset_format, pair.question, pair.answer, pair.record, to)
        if rec is None:
            # kept as it was, so switching back restores it
            pair.kept, pair.dropped_reason = False, "format_changed"
        else:
            formats.apply(pair, rec)


async def latest(db: AsyncSession, project_id: uuid.UUID) -> StyleConfig | None:
    return await db.scalar(
        select(StyleConfig).where(StyleConfig.project_id == project_id).order_by(StyleConfig.created_at.desc()).limit(1)
    )


def to_in(row: StyleConfig) -> StyleIn:
    return StyleIn.model_validate(
        {
            "template_key": row.template_key,
            "description": row.description,
            "tone": row.tone,
            "length": row.length,
            "format": row.format,
            "language": row.language,
            "examples": row.examples,
            "system_prompt_in_data": row.system_prompt_in_data,
            "dataset_format": row.dataset_format,
        }
    )


def to_spec(row: StyleConfig) -> StyleSpec:
    return StyleSpec(
        description=row.description,
        tone=row.tone,
        length=row.length,
        format=row.format,
        language=row.language,
        examples=list(row.examples),
        dataset_format=row.dataset_format,
    )
