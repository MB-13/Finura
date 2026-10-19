"""Dataset formats: the shape of each training example (ADR-0003).

Every format is stored in the same two columns plus an optional JSONB `record`:

| format      | question            | answer               | record                       |
|-------------|---------------------|----------------------|------------------------------|
| qa_chat     | question            | answer               | None                         |
| instruction | instruction         | output               | {"input": str} when present  |
| multi_turn  | first user turn     | last assistant turn  | {"middle": [turns between]}  |

so search, sorting, stats and the "avoid" list keep working on question/answer. All formats train as chat
messages through the base model's chat template, so the notebook and the playground need no change.
"""

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

DatasetFormat = Literal["qa_chat", "instruction", "multi_turn"]
DEFAULT_FORMAT: DatasetFormat = "qa_chat"

MAX_TURNS = 8
# a conversation's training text must fit the smallest training window (1024 tokens on large models)
MULTI_TURN_MAX_TOKENS = 1000


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class QaRecord(BaseModel):
    format: Literal["qa_chat"] = "qa_chat"
    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)


class InstructionRecord(BaseModel):
    format: Literal["instruction"] = "instruction"
    instruction: str = Field(min_length=3, max_length=2000)
    input: str = Field(default="", max_length=6000)
    output: str = Field(min_length=1, max_length=8000)


class ConversationRecord(BaseModel):
    format: Literal["multi_turn"] = "multi_turn"
    messages: list[Turn] = Field(min_length=2, max_length=MAX_TURNS)

    @model_validator(mode="after")
    def _alternates(self) -> "ConversationRecord":
        for i, turn in enumerate(self.messages):
            if turn.role != ("user" if i % 2 == 0 else "assistant"):
                raise ValueError("A conversation starts with the user and then alternates user and assistant turns")
        if self.messages[-1].role != "assistant":
            raise ValueError("A conversation must end with an assistant turn")
        return self


Record = QaRecord | InstructionRecord | ConversationRecord
PairRecord = Annotated[Record, Field(discriminator="format")]


class FormatInfo(BaseModel):
    key: DatasetFormat
    name: str
    description: str
    best_for: str
    # LLM tokens per example compared with Q&A chat; generation takes about this much longer
    relative_cost: float
    input_label: str
    output_label: str
    sample: PairRecord


FORMATS: dict[str, FormatInfo] = {
    "qa_chat": FormatInfo(
        key="qa_chat",
        name="Questions & answers",
        description="One question and one answer per example.",
        best_for="Assistants and FAQ bots that answer questions about your documents.",
        relative_cost=1.0,
        input_label="Question",
        output_label="Answer",
        sample=QaRecord(question="How long is the warranty?", answer="Two years from the date of purchase."),
    ),
    "instruction": FormatInfo(
        key="instruction",
        name="Instructions (Alpaca)",
        description="A task, an optional passage to work on, and the result.",
        best_for="Models that do jobs on text: summarize, extract, rewrite, classify or compare.",
        relative_cost=1.3,
        input_label="Instruction",
        output_label="Output",
        sample=InstructionRecord(
            instruction="List the steps in this procedure.",
            input="Unplug the device, wait ten seconds, then hold the power button while plugging it back in.",
            output="1. Unplug the device.\n2. Wait ten seconds.\n3. Hold the power button and plug it back in.",
        ),
    ),
    "multi_turn": FormatInfo(
        key="multi_turn",
        name="Conversations",
        description="Dialogues of two to four turns with follow-up questions.",
        best_for="Chat assistants that should keep context across follow-up questions.",
        relative_cost=3.0,
        input_label="Conversation",
        output_label="Last answer",
        sample=ConversationRecord(
            messages=[
                Turn(role="user", content="How long is the warranty?"),
                Turn(role="assistant", content="Two years from the date of purchase."),
                Turn(role="user", content="Does it cover water damage?"),
                Turn(role="assistant", content="No. Water damage is excluded, but accidental drops are covered."),
            ]
        ),
    ),
}

# pairs asked for per chunk in one call; conversations are longer, so fewer fit in one response
MAX_PER_CHUNK: dict[str, int] = {"qa_chat": 8, "instruction": 6, "multi_turn": 3}
_TOKENS_PER_ITEM: dict[str, int] = {"qa_chat": 400, "instruction": 600, "multi_turn": 1500}


def max_per_chunk(fmt: str) -> int:
    return MAX_PER_CHUNK.get(fmt, MAX_PER_CHUNK[DEFAULT_FORMAT])


def max_tokens(fmt: str, n: int) -> int:
    return min(8000, _TOKENS_PER_ITEM.get(fmt, 400) * n + 300)


def relative_cost(fmt: str) -> float:
    info = FORMATS.get(fmt)
    return info.relative_cost if info else 1.0


# ---------------- record <-> columns ----------------


def columns(rec: Record) -> tuple[str, str, dict[str, Any] | None]:
    """(question, answer, record) to store for a record."""
    if isinstance(rec, InstructionRecord):
        text = rec.input.strip()
        return rec.instruction.strip(), rec.output.strip(), {"input": text} if text else None
    if isinstance(rec, ConversationRecord):
        turns = [{"role": t.role, "content": t.content.strip()} for t in rec.messages]
        middle = turns[1:-1]
        return turns[0]["content"], turns[-1]["content"], {"middle": middle} if middle else None
    return rec.question.strip(), rec.answer.strip(), None


def apply(pair: Any, rec: Record) -> None:
    """The only writer of a pair's question/answer/record columns."""
    pair.dataset_format = rec.format
    pair.question, pair.answer, pair.record = columns(rec)


def view(fmt: str, question: str, answer: str, record: dict[str, Any] | None) -> PairRecord:
    if fmt == "instruction":
        return InstructionRecord(instruction=question, input=(record or {}).get("input", ""), output=answer)
    if fmt == "multi_turn":
        middle = [Turn.model_validate(t) for t in (record or {}).get("middle", [])]
        return ConversationRecord(
            messages=[Turn(role="user", content=question), *middle, Turn(role="assistant", content=answer)]
        )
    return QaRecord(question=question, answer=answer)


def messages(fmt: str, question: str, answer: str, record: dict[str, Any] | None) -> list[dict[str, str]]:
    """The user/assistant turns the model trains on."""
    if fmt == "instruction":
        text = (record or {}).get("input", "")
        user = f"{question}\n\n{text}" if text else question
        return [{"role": "user", "content": user}, {"role": "assistant", "content": answer}]
    middle = list((record or {}).get("middle", [])) if fmt == "multi_turn" else []
    return [{"role": "user", "content": question}, *middle, {"role": "assistant", "content": answer}]


def convert(pair_format: str, question: str, answer: str, record: dict[str, Any] | None, to: str) -> Record | None:
    """Re-shape a user-added pair for a new format, or None when it can't be done without losing turns."""
    turns = messages(pair_format, question, answer, record)
    if len(turns) != 2:
        return None
    user, assistant = turns[0]["content"], turns[1]["content"]
    if to == "instruction":
        return InstructionRecord(instruction=user, output=assistant)
    if to == "multi_turn":
        return ConversationRecord(messages=[Turn(role="user", content=user), Turn(role="assistant", content=assistant)])
    return QaRecord(question=user, answer=assistant)


# ---------------- per-format views used by generation, finalize and export ----------------


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def dedupe_key(fmt: str, question: str, record: dict[str, Any] | None) -> str:
    """Exact-duplicate key. The same instruction on a different input is a different example."""
    if fmt == "instruction":
        return _norm(f"{question} {(record or {}).get('input', '')}")
    return _norm(question)


def embed_text(fmt: str, question: str, answer: str, record: dict[str, Any] | None) -> str:
    return "\n".join(m["content"] for m in messages(fmt, question, answer, record))[:4000]


def judge_text(fmt: str, question: str, answer: str, record: dict[str, Any] | None) -> str:
    """How one example is shown to the judge."""
    if fmt == "instruction":
        text = (record or {}).get("input", "")
        return f"Instruction: {question}\n" + (f"Input: {text}\n" if text else "") + f"Output: {answer}"
    if fmt == "multi_turn":
        return "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages(fmt, question, answer, record)
        )
    return f"Q: {question}\nA: {answer}"


def assistant_texts(fmt: str, question: str, answer: str, record: dict[str, Any] | None) -> list[str]:
    return [m["content"] for m in messages(fmt, question, answer, record) if m["role"] == "assistant"]


def training_line(fmt: str, question: str, answer: str, record: dict[str, Any] | None, system: str | None) -> str:
    msgs = [{"role": "system", "content": system}] if system else []
    msgs += messages(fmt, question, answer, record)
    return json.dumps({"messages": msgs}, ensure_ascii=False)


def native_line(fmt: str, question: str, answer: str, record: dict[str, Any] | None, system: str | None) -> str:
    """The format's own well-known layout, for use outside DocTune (Alpaca, ShareGPT)."""
    if fmt == "instruction":
        row: dict[str, Any] = {"instruction": question, "input": (record or {}).get("input", ""), "output": answer}
        if system:
            row["system"] = system
        return json.dumps(row, ensure_ascii=False)
    if fmt == "multi_turn":
        convs = [{"from": "system", "value": system}] if system else []
        convs += [
            {"from": "human" if m["role"] == "user" else "gpt", "value": m["content"]}
            for m in messages(fmt, question, answer, record)
        ]
        return json.dumps({"conversations": convs}, ensure_ascii=False)
    return training_line(fmt, question, answer, record, system)
