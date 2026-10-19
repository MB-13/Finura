"""Versioned prompts. Change the text => bump the version (stored on each generation run)."""

import json
from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, Field

GEN_VERSION = "gen-v1"
JUDGE_VERSION = "judge-v1"
GEN_VERSIONS = {"qa_chat": GEN_VERSION, "instruction": "gen-instruction-v1", "multi_turn": "gen-multiturn-v1"}

_env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)  # noqa: S701 - plain-text prompts, not HTML

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "gu": "Gujarati",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ja": "Japanese",
    "zh": "Chinese",
    "ar": "Arabic",
}

# the design-doc template, plus language and a JSON object wrapper (JSON mode needs an object)
GENERATION = _env.from_string(
    """You are creating training data for a fine-tuned AI model.

SOURCE TEXT:
{{ chunk }}

USER'S DESIRED OUTPUT STYLE:
{{ description }}
Tone: {{ tone }} | Length: {{ length }} | Format: {{ format }}
{% if language != "English" %}Language: write questions and answers in {{ language }}.
{% endif %}

EXAMPLES OF THE DESIRED STYLE:
{% for ex in examples %}
Example {{ loop.index }}
Input: {{ ex.input }}
Output: {{ ex.output }}
{% endfor %}

TASK:
Write {{ n }} new question-answer pairs based ONLY on the source text.
- Answers must follow the style shown in the examples exactly.
- Do not copy the examples' topics or wording; match only their style.
- Vary the question types: factual, explanatory, and how-to.
- If the source text doesn't support an answer, don't invent one.
{% if avoid %}- These questions already exist. Ask about different facts or angles, never the same thing reworded:
{% for q in avoid %}  - {{ q }}
{% endfor %}{% endif %}{% if format == "json" %}- Each answer must itself be a valid JSON value, written as a string.
{% endif %}

Return JSON: {"pairs": [{"question": "...", "answer": "..."}]}"""
)


GENERATION_INSTRUCTION = _env.from_string(
    """You are creating instruction-tuning data (Alpaca style) for a fine-tuned AI model.

SOURCE TEXT:
{{ chunk }}

USER'S DESIRED OUTPUT STYLE:
{{ description }}
Tone: {{ tone }} | Length: {{ length }} | Format: {{ format }}
{% if language != "English" %}Language: write instructions, inputs and outputs in {{ language }}.
{% endif %}

EXAMPLES OF THE DESIRED STYLE:
{% for ex in examples %}
Example {{ loop.index }}
Input: {{ ex.input }}
Output: {{ ex.output }}
{% endfor %}

TASK:
Write {{ n }} new examples based ONLY on the source text. Each example is a task for the model:
- "instruction": what to do, e.g. summarize, extract specific facts, rewrite for an audience, explain, compare,
  turn into a checklist, classify. Vary the kinds of task.
- "input": a short passage copied from the source text that the task works on (at most about 150 words), or ""
  when the instruction stands on its own.
- "output": the result, following the style shown in the examples exactly.
- Do not copy the examples' topics or wording; match only their style.
- If the source text doesn't support an output, don't invent one.
{% if avoid %}- These instructions already exist. Cover different facts or angles, never the same thing reworded:
{% for q in avoid %}  - {{ q }}
{% endfor %}{% endif %}{% if format == "json" %}- Each output must itself be a valid JSON value, written as a string.
{% endif %}

Return JSON: {"items": [{"instruction": "...", "input": "...", "output": "..."}]}"""
)

GENERATION_MULTI_TURN = _env.from_string(
    """You are creating multi-turn conversation data for a fine-tuned AI chat model.

SOURCE TEXT:
{{ chunk }}

USER'S DESIRED OUTPUT STYLE:
{{ description }}
Tone: {{ tone }} | Length: {{ length }} | Format: {{ format }}
{% if language != "English" %}Language: write every turn in {{ language }}.
{% endif %}

EXAMPLES OF THE DESIRED STYLE:
{% for ex in examples %}
Example {{ loop.index }}
Input: {{ ex.input }}
Output: {{ ex.output }}
{% endfor %}

TASK:
Write {{ n }} new conversations based ONLY on the source text, each with 2 to 4 user turns.
- The first user message asks about something in the source text.
- Each later user message is a natural follow-up: it asks for more detail, clarifies, or goes deeper, and may
  refer back with words like "it" or "that".
- Every assistant message follows the style shown in the examples exactly and uses only the source text.
- Keep each conversation short enough to read in a minute.
- Do not copy the examples' topics or wording; match only their style.
- If the source text doesn't support an answer, don't invent one.
{% if avoid %}- These opening questions already exist. Cover different facts or angles, never the same thing reworded:
{% for q in avoid %}  - {{ q }}
{% endfor %}{% endif %}{% if format == "json" %}- Each assistant message must be valid JSON, written as a string.
{% endif %}

Return JSON: {"conversations": [{"messages": [
  {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}]}"""
)

JUDGE = _env.from_string(
    """You are reviewing training data for a fine-tuned AI model. Score every pair strictly.

SOURCE TEXT:
{{ chunk }}

REQUIRED STYLE:
{{ description }}
Tone: {{ tone }} | Length: {{ length }} | Format: {{ format }}
Example of the style: {{ example_output }}

PAIRS:
{% for p in pairs %}
[{{ p.id }}]
{{ p.text }}
{% endfor %}

For each pair give:
- correctness 1-5: {{ correctness_rule }}
- style 1-5: {{ style_rule }}
- reason: at most 20 words

Return JSON: {"scores": [{"id": "p1", "correctness": 5, "style": 4, "reason": "..."}]}"""
)


class GeneratedInstruction(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)
    input: str = Field(default="", max_length=6000)
    output: str = Field(min_length=1, max_length=4000)


class InstructionGenOut(BaseModel):
    items: list[GeneratedInstruction]


class GeneratedTurn(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=4000)


class GeneratedConversation(BaseModel):
    # roles and order are checked per conversation, so one malformed conversation doesn't fail the whole call
    messages: list[GeneratedTurn] = Field(min_length=2)


class ConversationGenOut(BaseModel):
    conversations: list[GeneratedConversation]


class GeneratedPair(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


class GenerationOut(BaseModel):
    pairs: list[GeneratedPair]


class Score(BaseModel):
    id: str
    correctness: int = Field(ge=1, le=5)
    style: int = Field(ge=1, le=5)
    reason: str = ""


class JudgeOut(BaseModel):
    scores: list[Score]


@dataclass
class StyleSpec:
    description: str
    tone: str
    length: str
    format: str
    language: str
    examples: list[dict[str, str]]
    dataset_format: str = "qa_chat"


_GENERATION_TEMPLATES = {"instruction": GENERATION_INSTRUCTION, "multi_turn": GENERATION_MULTI_TURN}

# what "correctness" and "style" mean for each format; Q&A keeps the original wording
_JUDGE_RULES = {
    "qa_chat": (
        "5 = fully supported by the source text, 1 = contradicts it or invents facts",
        "5 = matches the required style exactly, 1 = ignores it",
    ),
    "instruction": (
        "5 = the output does exactly what the instruction asks and is fully supported by the source text, "
        "1 = ignores the instruction, contradicts the source or invents facts",
        "5 = the output matches the required style exactly, 1 = ignores it",
    ),
    "multi_turn": (
        "score the WEAKEST assistant turn: 5 = every answer is supported by the source text and every "
        "follow-up question makes sense after the earlier turns, "
        "1 = any answer contradicts the source or invents facts",
        "5 = every assistant turn matches the required style exactly, 1 = the style is ignored or drifts",
    ),
}


def generation_messages(style: StyleSpec, chunk: str, n: int, avoid: list[str] | None = None) -> list[dict[str, str]]:
    template = _GENERATION_TEMPLATES.get(style.dataset_format, GENERATION)
    prompt = template.render(
        chunk=chunk,
        description=style.description,
        tone=style.tone,
        length=style.length,
        format=style.format,
        language=LANGUAGES.get(style.language, style.language),
        examples=style.examples,
        n=n,
        avoid=avoid or [],
    )
    return [{"role": "user", "content": prompt}]


def judge_messages(style: StyleSpec, chunk: str, pairs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """`pairs`: [{"id": "p1", "text": <the example as formats.judge_text renders it>}]."""
    example = style.examples[0]["output"] if style.examples else ""
    correctness_rule, style_rule = _JUDGE_RULES.get(style.dataset_format, _JUDGE_RULES["qa_chat"])
    prompt = JUDGE.render(
        correctness_rule=correctness_rule,
        style_rule=style_rule,
        chunk=chunk,
        description=style.description,
        tone=style.tone,
        length=style.length,
        format=style.format,
        example_output=example[:600],
        pairs=pairs,
    )
    return [{"role": "user", "content": prompt}]


def to_chat_record(question: str, answer: str, system_prompt: str | None) -> str:
    messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
    messages += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return json.dumps({"messages": messages}, ensure_ascii=False)


EVAL_VERSION = "eval-v1"

EVAL_JUDGE = _env.from_string(
    """You are evaluating two AI models on the same questions. For each item compare BOTH answers with the
reference answer (which is correct and in the desired style).

REQUIRED STYLE:
{{ description }}

{% for it in items %}
[{{ it.id }}]
{% if it.context %}Earlier in the conversation:
{{ it.context }}
{% endif %}
Question: {{ it.question }}
Reference: {{ it.reference }}
Answer A: {{ it.base_answer }}
Answer B: {{ it.tuned_answer }}
{% endfor %}

Score each answer 1-5 for correctness (agrees with the reference, no invented facts) and 1-5 for style
(matches the required style and the reference's style).

Return JSON: {"scores": [{"id": "e1", "a_correctness": 3, "a_style": 2, "b_correctness": 5, "b_style": 5}]}"""
)


class EvalScore(BaseModel):
    id: str
    a_correctness: int = Field(ge=1, le=5)
    a_style: int = Field(ge=1, le=5)
    b_correctness: int = Field(ge=1, le=5)
    b_style: int = Field(ge=1, le=5)


class EvalOut(BaseModel):
    scores: list[EvalScore]


def eval_messages(description: str, items: list[dict[str, str]]) -> list[dict[str, str]]:
    items = [{"context": "", **it} for it in items]
    return [{"role": "user", "content": EVAL_JUDGE.render(description=description, items=items)}]
