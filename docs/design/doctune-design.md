## DocTune — Project Design Document

Oct 6, 2026 · @Engineer 9spl

### Overview

DocTune (working name) is a web platform where a user uploads documents, describes how they want the model to respond, and gets back a fine-tuned open-source model, with no ML knowledge needed. The platform generates the training dataset automatically, trains with QLoRA, and delivers downloadable weights plus a chat playground to test the result.

It is similar to managed fine-tuning services, with two differences: the dataset is generated for the user from their documents, and training runs free on the user's own Google Colab GPU.

Target users: developers, students, startups and small teams who want a custom model but lack ML expertise or GPU budget.

Constraint: every part of the stack must be free (free tiers or open source).

### Core features

| Feature | What it does |
|---|---|
| Document upload | Upload PDF, DOCX, TXT or Markdown files straight to storage |
| Style guidance | User describes the desired output in words, gives 2–5 examples, and picks tone, length, format and language |
| Templates and style profiles | Presets (support bot, tech docs assistant, JSON extractor) and saved, reusable styles |
| Preview loop | Generate 5–10 sample pairs, tweak the style, regenerate before the full run |
| Automatic dataset generation | Q&A and instruction pairs built from every document chunk, matching the user's style |
| Quality filtering | LLM judge checks correctness and style; duplicates removed |
| Dataset review | Editable table to delete, fix or add examples before training |
| Training notebook | DocTune provides a notebook the user opens in Google Colab and runs on the free T4 GPU; no Google credentials are stored |
| Checkpoint and resume | Training saves progress to R2; the user re-runs the notebook and it continues from the last checkpoint |
| Evaluation | Base model vs fine-tuned model scored on a held-out 10% of the data |
| Weight export | LoRA adapter (safetensors), merged weights, and GGUF for Ollama or llama.cpp |
| Chat playground | Chat with the fine-tuned model in the browser |
| Notifications | Email when training pauses, resumes or finishes |

### Key design decisions

Fine-tuning teaches behavior; RAG supplies facts. Fine-tuning reliably teaches style, tone and format, but is weak at memorizing facts from a document. The chat playground will therefore combine the fine-tuned model with retrieval over the user's own document chunks (RAG), so answers are both in the right style and factually grounded.

User-guided dataset generation. The user's description and examples are injected into the generation prompt. Generation always runs as a cheap preview first, and the full run starts only after the user approves.

Style is baked into the data. By default the style lives in the training examples, so the model behaves that way with no special prompt. An advanced toggle also adds the description as a system prompt in every example.

QLoRA by default. 4-bit QLoRA fits models up to roughly 7–8B parameters on a 16 GB T4. Hyperparameters are hidden behind presets, with an advanced panel for power users.

Pluggable training compute. Training goes through one backend interface (submit_job, get_status, get_output, cancel). The user-run notebook is the first backend and runs on Google Colab, with Kaggle, Lightning AI or a local GPU possible later; a paid GPU backend can be added later without changing the rest of the system.

Everything asynchronous. Web requests only save records and queue jobs. Workers do all slow work, and the UI follows a job status field.

### Model selection

Users choose both the base model to fine-tune and the model that generates their dataset; safe defaults are preselected.

Base model: curated list (default). Cards show size, license, whether it fits a free T4, and a rough training-time hint.

| Model | Size | License | Fits free T4 |
|---|---|---|---|
| Qwen3.5 4B (recommended) | 4B | Apache 2.0 | Yes |
| Qwen3 0.6B / 1.7B / 4B | 0.6–4B | Apache 2.0 | Yes |
| Qwen3.5 0.8B / 2B | 0.8–2B | Apache 2.0 | Yes |
| Qwen3 8B / Qwen3.5 9B ("large") | 8–9B | Apache 2.0 | Yes with QLoRA; to be confirmed in testing |

Base model: custom (advanced). The user pastes any Hugging Face model ID. The backend checks it through the Hugging Face API before accepting:

- Architecture is supported by Unsloth.
- Size fits a 16 GB T4 with QLoRA (block above ~10B).
- License tag: Apache 2.0 or MIT passes; anything else shows a warning the user must acknowledge.
- Gated models (Llama, Gemma) need the user's own Hugging Face token, entered in the notebook, not stored by DocTune.
Automatic license compliance. For Llama models the output is named "Llama-…", the license notice file is included in the download, and the "Built with Llama" duty is shown to the user.

Generation model. Users pick a provider and model from the keys they connected; the default is Groq with an Apache 2.0 open model (see Dataset generation).

Each project stores the base model ID, its license, and the generation provider and model; training, export and the playground all read from it.

### User flow

end-to-end user flow · dataset phase, then training phase

The top row builds the dataset cheaply and loops until the preview looks right; the second row spends GPU time only after the user approves the reviewed dataset. Training runs in a notebook the user opens in Google Colab; when a session or quota ends, the user re-runs it and it continues from the last checkpoint.

### Dataset generation

The dataset is generated chunk by chunk, guided by the user's style, then filtered before anyone trains on it.

Inputs from the user

- A free-text description of the desired output (e.g. "friendly support agent, short sentences, end by offering more help")
- 2–5 example input/output pairs
- Dropdowns: tone, length, format (plain text, bullets, JSON), language
- Or a template, which pre-fills all of the above
Generation prompt template

```
You are creating training data for a fine-tuned AI model.

SOURCE TEXT:
{chunk}

USER'S DESIRED OUTPUT STYLE:
{user_description}
Tone: {tone} | Length: {length} | Format: {format}

EXAMPLES OF THE DESIRED STYLE:
{user_examples}

TASK:
Write {n} new question-answer pairs based ONLY on the source text.
- Answers must follow the style shown in the examples exactly.
- Do not copy the examples' topics or wording; match only their style.
- Vary the question types: factual, explanatory, and how-to.
- If the source text doesn't support an answer, don't invent one.

Return JSON: [{"question": "...", "answer": "..."}]
```

Processing steps

- Parse documents (Docling or PyMuPDF, OCR for scans) and split into section-aware chunks of a few hundred to ~1,000 tokens.
- Preview: run the prompt on a few random chunks; the user iterates until satisfied.
- Full run: fan out over all chunks in parallel.
- Filter: an LLM judge scores each pair on correctness against the source and adherence to the style; failures are dropped.
- Deduplicate near-identical pairs.
- Split off 10% as a held-out evaluation set.
- User review in an editable table, then export as JSONL in chat format.
Where generation runs: bring your own key. Free LLM tiers are rate-limited per account, so one shared key cannot serve many users. Each user pastes their own free API key in settings, which gives every user their own full free quota at zero cost to us. Privacy is out of scope for this project, but the privacy policy must still state that uploaded documents are sent to third-party AI providers.

| Provider | Free limits (reported, verify before use) | Role |
|---|---|---|
| Gemini API | Most generous free tier, tight per-minute limits; not available in the EU/UK | Optional (user accepts Google's terms) |
| Groq | ~30 requests/min, 250–1,000/day per model, per organization | Default (Apache 2.0 models such as Qwen3, GPT-OSS) |
| Cerebras | ~1M tokens/day reported; some sources say a card is now required | Optional, if the user's account still has free access |
| Open model in the user's Colab notebook | Limited by the user's GPU quota | Last-resort fallback |

Fallback chain. All providers are called through one OpenAI-compatible client with a configurable base URL. On a rate-limit error the worker waits and retries, then moves to the next provider the user has connected. If every provider is exhausted, the generation job pauses and resumes later, the same way training does. A ~2,000-pair dataset including the filter pass is roughly several hundred thousand to ~1M tokens (estimate), about one day of a generous free quota.

Example validation: warn the user when they provide only one example or examples that contradict each other.

Dataset formats (ADR-0003). Before the preview the user picks the shape of every training example:

- Questions & answers (default): one question and one answer.
- Instructions (Alpaca): a task such as summarize, extract or rewrite, an optional passage from the documents to work on, and the result.
- Conversations: dialogues of two to four turns with follow-up questions. About 3× the LLM quota per example.

The format drives generation, judging and the review table. Every format trains as chat messages through the base model's chat template, so training, the playground and Ollama work the same for all of them; the native layouts (Alpaca, ShareGPT) are available as an export. Prompt–completion and preference (DPO) data are possible later; raw text, tool calling and multimodal data are out of scope.

### Training: user-run Colab notebook

Training runs in a Google Colab notebook that the user opens in their own Google account, on Colab's free T4 GPU. DocTune never stores Google credentials or runs anything in the user's account. Colab's free tier has no fixed quota: sessions last at most 12 hours, runtimes time out when idle, GPU access is not guaranteed, limits are unpublished and fluctuate, and there is no background execution.

How a training run works

- User approves the dataset and picks a base model, then clicks Start training.
- Backend creates the job and a job token: valid for this one job only, expires after 14 days, revocable from the dashboard.
- User clicks Open in Colab, which opens the DocTune template notebook hosted on GitHub, and pastes the job token into the first cell.
- User selects Runtime → Change runtime type → T4 GPU, runs the cells in order, and keeps the tab open.
- The notebook calls the DocTune API with the token: fetches the config, downloads the dataset through a pre-signed URL, installs Unsloth, loads the base model in 4-bit, and trains with QLoRA in fp16 (T4s lack bf16).
- A progress bar shows inside the notebook, and heartbeats with step and loss drive the dashboard chart.
- On finish, it runs evaluation, uploads the LoRA adapter to R2, and saves merged weights and GGUF to the user's own Google Drive (and Hugging Face, if the user enters their own token in the notebook).
```
from getpass import getpass
JOB_TOKEN = getpass("Paste your DocTune job token: ")  # one job only, expires in 14 days
API = "https://api.doctune.example"

H = {"Authorization": f"Bearer {JOB_TOKEN}"}
cfg = requests.get(f"{API}/jobs/current/config", headers=H).json()
ckpt = requests.get(f"{API}/jobs/current/checkpoint/latest", headers=H).json()
# download dataset + latest checkpoint (if any), then train / resume
```

Checkpoint and resume

- Save a checkpoint every 5–10 minutes, since free Colab sessions can end without warning: LoRA weights, optimizer state, LR scheduler state and step number.
- Upload each checkpoint to R2 immediately through a pre-signed URL; keep only the latest one per job.
- Resuming = the user opens the notebook again and runs the cells. It asks the API for the latest checkpoint and calls trainer.train(resume_from_checkpoint=path) with the same dataset, seed and library versions.
- If no heartbeat arrives for 15 minutes, the backend marks the job paused and emails the user.
```
from transformers import TrainerCallback

class UploadCheckpoint(TrainerCallback):
    def on_save(self, args, state, control, **kwargs):
        ckpt = f"{args.output_dir}/checkpoint-{state.global_step}"
        upload_folder(ckpt, state.global_step)  # zip + PUT via pre-signed URL
        heartbeat(state.global_step, state.max_steps)
```

Pause handling

| Pause reason | What happens | Message to the user |
|---|---|---|
| Session ended (12-hour cap or Colab reclaimed the GPU) | Last checkpoint is kept | "Your Colab session ended at 64%. Progress is saved. Open the notebook and run it again to continue." |
| Idle timeout | Tab left without interaction; runtime disconnects | "Colab disconnected because the tab was idle. Progress is saved at 64%. Run the notebook again and keep the tab open." |
| No GPU available | Colab usage limit reached for now | "Colab has no free GPU for your account right now. Progress is saved at 64%. Try again later." |
| Notebook stopped or crashed | No heartbeat for 15 minutes | "Training stopped at 64%. Progress is saved. Run the notebook again to continue." |

While paused, the user can download the latest checkpoint and test it in the playground.

Staying within Colab's free-tier rules. Colab's FAQ bans file hosting and web services, proxies, mining and using multiple accounts on all runtimes, and on the free tier also SSH or remote desktops, web UIs that bypass the notebook, and distributed computing workers. So the notebook stays interactive: the user runs the cells and watches progress, one job per notebook, no headless runs, and no web UI served from Colab.

Not locked to Colab. The notebook needs only Python, a GPU and internet access, so Kaggle, Lightning AI or a local GPU can be added later as options. Kaggle is dropped for now because its terms allow only personal, non-commercial use, not on behalf of a third party.

### Architecture and job states

system architecture · 9 components

The API never does slow work: it writes a record, queues a job and returns. Workers parse documents and call the LLM. Training happens in the user's own Colab notebook, which talks to the API with a one-job token, writes checkpoints and the final adapter straight to R2, and sends heartbeats that the API stores in Postgres for the UI.

Each project moves through one status field that the UI reads to decide which screen to show:

| Status | Meaning | Moved by |
|---|---|---|
| uploaded | Files stored in R2 | API |
| parsing | Text extraction and chunking | Parse worker |
| awaiting_style | Waiting for the user's style input | User |
| previewing | Sample pairs being generated | Generation worker |
| generating | Full dataset generation and filtering | Generation worker |
| in_review | User editing and approving the dataset | User |
| awaiting_run | Notebook generated; waiting for the user to run it | User |
| training | Notebook running in the user's Colab session | Notebook heartbeat (job token) |
| paused | Session or quota limit hit; reason stored | Notebook, or heartbeat monitor after 15 min of silence |
| evaluating | Base vs tuned scoring | Notebook (after training) |
| ready | Weights and playground available | Notebook |
| failed | Unrecoverable error; message shown | Any worker |

### Tech stack (all free)

Every component is open source or on a free tier. Free-tier limits change, so verify each provider's current terms before committing.

| Layer | Choice |
|---|---|
| Frontend | Next.js + Tailwind CSS + shadcn/ui, hosted on Cloudflare Pages |
| Backend API | FastAPI (Python) |
| Server (backend, workers, Redis) | Oracle Cloud Always Free ARM VM |
| Database | Supabase free tier (Postgres + pgvector) |
| Auth | Supabase Auth |
| File storage | Cloudflare R2 free tier |
| Job queue | Celery + Redis, self-hosted on the Oracle VM |
| Document parsing | Docling or PyMuPDF (+ OCR) |
| Dataset generation | User's own free API key (Groq default; Gemini, Cerebras optional) via an OpenAI-compatible client, with an open model in the user's Colab notebook as fallback |
| Fine-tuning | Unsloth + Hugging Face TRL/PEFT (QLoRA) |
| Training compute | User-run notebook on the user's free Google Colab T4 |
| Checkpoints | Hugging Face Trainer checkpoints stored in R2 |
| Chat playground | llama.cpp (GGUF) on the Oracle VM CPU, plus RAG over pgvector |
| Export | safetensors adapters, merged weights, GGUF via llama.cpp |
| Real-time updates | Server-Sent Events |
| Email | Resend free tier |
| Monitoring | Sentry free tier, Weights & Biases free tier |
| Payments (later) | Stripe (no monthly fee) |

CPU chat works well for 1–3B models but is slow for 7B+; users can also download the GGUF and chat locally in Ollama. The only likely cost is a custom domain (~$10/year); launch on a free subdomain first.

### Risks and limitations

| Risk | Impact | Mitigation |
|---|---|---|
| Colab free-tier rules | Free tier bans SSH, web UIs, distributed workers and multiple accounts; runtimes may be terminated without warning | Notebook stays interactive: the user runs the cells, one job per notebook, no headless runs or web UI; DocTune holds no Google credentials; the notebook can also run on Kaggle, Lightning AI or a local GPU |
| Credential security | Users' LLM API keys and job tokens could leak | Encrypt LLM keys at rest and never log them; job tokens are scoped to one job, expire in 14 days and can be revoked |
| Colab limits and reliability | Limits are unpublished and fluctuate, GPUs are not guaranteed, and the free tier has no background execution | Checkpoints every 5–10 minutes; resume by re-running; pause emails; notebook runs on any GPU platform |
| LLM API terms | Some providers restrict using outputs to train other models | Users bring their own API keys, so each provider's terms apply to their own account; fall back to an open model in the user's Colab notebook |
| Fine-tuning won't memorize facts | Users expect document Q&A and get hallucinations | RAG in the playground; set expectations in onboarding |
| Base model licenses | Some open models restrict commercial use | Offer only models whose licenses fit; show the license per model |
| User data privacy | Business documents are sensitive | Private kernels, encrypted storage, full deletion, no training on user data |
| Free-tier limits | Storage caps, rate limits, sleeping servers | Enforce upload and dataset size limits; monitor usage |
| Malicious uploads | Oversized or harmful files | Validate type and size; parse in isolated workers |
| Colab idle timeout | Session disconnects when the tab is left without interaction (reported around 90 minutes) | Show live progress inside the notebook; tell users to keep the tab open; frequent checkpoints |

### Roadmap

Build the end-to-end path once with one file type and one model, then widen it.

- Foundation: auth, project dashboard, PDF upload to R2, parsing and chunking, job queue and status tracking. Done when an uploaded PDF shows its chunks.
- Dataset generation (core product): style form, templates, preview loop, full generation, filtering, review table, JSONL export. Done when a user approves a dataset they like.
- Colab training: job tokens, notebook generator, train.py template, heartbeat tracking, adapter upload. Done when one model trains end to end.
- Checkpoint and resume: checkpoint uploads, graceful stop, pause states, resume by re-running, email notifications.
- Delivery: chat playground with RAG, evaluation scores, GGUF and merged-weight export.
- Growth: more file types and base models, saved style profiles, a paid GPU backend, Stripe billing.
### Decisions log

Every open question now has a decision. Training runs on Google Colab only; Kaggle is dropped for now. Two checks remain before launch (a Google terms review and name registration), and neither blocks building.

| Question | Decision | Status |
|---|---|---|
| Which free GPU platform? | Google Colab only. Users open the notebook in their own Google account and run the cells themselves; DocTune stores no Google credentials (see Training). Colab's rules list banned activities but, unlike Kaggle's terms, include no personal-use-only clause. Kaggle is dropped for now; the portable notebook lets it return later. | Resolved by design |
| Does the notebook fit Colab's free-tier rules? | Yes, as long as it stays interactive: the user runs the cells and watches progress, one job per notebook, no headless runs and no web UI served from Colab. Review the Google Terms of Service and Colab Additional Terms before launch. | Resolved; terms review on the launch checklist |
| Which base models? | Curated Qwen3 / Qwen3.5 list (Apache 2.0), plus a custom model option with automatic checks (see Model selection). | Resolved |
| Which LLM generates datasets? | Default: Groq with Apache 2.0 open models such as Qwen3 or GPT-OSS. Groq's terms say outputs fall under the model owner's terms, and Groq does not train on API data. Gemini: optional; the user acknowledges Google's terms, including its no-competing-models clause. Cerebras: optional, only if the user's account still has free access. Last resort: an open model inside the notebook. | Resolved |
| Privacy | Out of scope. The privacy policy states that documents are sent to third-party AI providers. | Resolved |
| Free-tier storage limits | R2 holds only adapters and the latest checkpoint, deleted 14 days after the job ends. Caps: 20 MB per file, 50 MB per project, 2,000 training pairs. Merged weights and GGUF stay in the user's notebook output or Hugging Face account. | Resolved |
| Product name and domain | Name: DocTune. A quick search found no AI fine-tuning product using it. Launch on the free doctune.pages.dev subdomain. | Resolved; registration checks on the launch checklist |

Launch checklist

- ☐ Review the Google Terms of Service and Colab Additional Terms; confirm the notebook stays within Colab's free-tier rules
- ☐ Check doctune.dev / doctune.app, GitHub and Hugging Face org names, and run a basic trademark search
- ☐ Re-verify free tiers and terms for Groq, Gemini and Cerebras
- ☐ Publish privacy policy and terms of use (third-party AI processing, Colab disclaimer)
- ☐ Confirm Qwen3 8B / Qwen3.5 9B QLoRA fits on a T4
Sources (as of 2026-10-06): Colab FAQ · Colab Additional Terms of Service · Kaggle Terms of Use · Kaggle Acceptable Use Policy · Gemini API Additional Terms · Groq terms archive · Groq data policies summary · Groq rate limits summary · Qwen 3 release notes · Llama 3.1 license text · Supabase pricing 2026 · Cloudflare R2 pricing

