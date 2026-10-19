# ADR-0003 — User-selectable dataset formats

Date: 2026-10-14 · Status: **Accepted (phase 1 built)**

## Context
Every project used to produce single-turn question/answer chat pairs. Users want to choose the shape of the dataset before generation, and have that choice drive generation, review, export and training. The usual shapes are chat Q&A, Alpaca-style instructions, prompt–completion, multi-turn conversations, preference pairs (DPO/KTO), raw text, tool calling, classification and multimodal.

Constraints: free tiers only (per-user Groq quotas), a T4 with 16 GB in fp16, Qwen3.5 4B 16-bit LoRA by default (Qwen3 QLoRA), at most 2,000 examples, a preview before every full run, and one non-thinking chat template across training, evaluation, Ollama and the playground (ADR-0001). `style_configs.format` already means the *answer* format (plain/bullets/json/markdown).

## Decision
1. A new `dataset_format` (`qa_chat` | `instruction` | `multi_turn`) lives on the immutable `style_configs` snapshot. Changing it is a style change: a new preview is required, and "Change style & regenerate" discards generated data. The format is frozen on `dataset_versions` at approval. Labels in the UI: "Dataset format", next to the existing "Format" of each answer.
2. Every pair keeps `question`/`answer` as its first prompt and last reply. A nullable JSONB `record` holds only the rest: `{"input"}` for an instruction, `{"middle": [turns]}` for a conversation. Search, sorting, stats and the "avoid these questions" list keep working unchanged. Only `services/formats.py` writes these columns, and a Pydantic discriminated union (`PairOut.record`) validates every write and is the API view.
3. All three formats train as chat messages through the base model's chat template. Alpaca's original "### Instruction:" text template is not used, because llama.cpp and Ollama only speak the chat template; the instruction's input follows it in the user message after a blank line. The native layouts (Alpaca, ShareGPT) are offered as an export. As a result **the notebook, training, the playground and Ollama need no change**: the existing `train_on_responses_only` already trains every assistant turn of a conversation.
4. Per format: its own generation prompt, judge rubric (conversations score the weakest assistant turn), items per call (8 / 6 / 3), output token budget, exact-duplicate key (an instruction on a different input is a different example) and relative LLM cost shown to the user (1× / 1.3× / 3×). Conversations are capped at 1,000 tokens so they fit the smallest training window (1,024 on large models).
5. User-added pairs survive a format change: a single question and answer is re-shaped into the new format; a longer conversation can't become one question, so it is set aside unchanged (`dropped_reason = format_changed`) and comes back if the format is switched back. Approval refuses kept pairs in another format.
6. Evaluation is unchanged except that, for conversations, the scorer adds the earlier turns from `eval.jsonl` so the judge can follow up-questions like "and how does it work?".

## Not now
- **Prompt–completion** (phase 2a): through the chat template it is the same as Q&A, so it only makes sense as raw text without a template. That needs a new notebook training path, a "complete the text" playground mode without document search, and a different Ollama template.
- **Preference / DPO** (phase 2b): needs a DPO training stage (adapter-off reference, no second model copy) and a T4 memory spike first. Likely fits Qwen3 4B QLoRA; borderline for Qwen3.5 4B 16-bit.
- **Raw text**: conflicts with "fine-tuning teaches behaviour, RAG supplies facts", has nothing for the judge to score, and the chat playground couldn't show what it learned.
- **Tool calling, KTO, GRPO, classification, multimodal**: documents have no tools; paired DPO beats unpaired KTO when we generate the pairs; GRPO needs a verifiable reward and is too heavy for a T4; classification is an instruction with label outputs; parsing produces text only.

## Consequences
- Conversations use about 3× the LLM tokens per example and give at most 3 per document section, so small document sets reach fewer examples. The estimate and the picker show this.
- The review table, add dialog and preview cards render and edit each format.
- Existing projects are unaffected: the defaults describe them exactly and their style hashes don't change.
