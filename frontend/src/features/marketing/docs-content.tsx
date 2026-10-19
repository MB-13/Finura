import type { ReactNode } from 'react'
import { Link } from 'react-router'

export type DocPage = {
  slug: string
  title: string
  summary: string
  body: ReactNode
}

const ext = (href: string, text: string) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
    {text}
  </a>
)

export const DOCS: DocPage[] = [
  {
    slug: 'groq-key',
    title: 'Get a free Groq key',
    summary: 'DocTune uses your own free key to write training examples.',
    body: (
      <>
        <ol>
          <li>Go to {ext('https://console.groq.com/keys', 'console.groq.com/keys')} and sign up. No payment method is needed.</li>
          <li>
            Choose <strong>Create API key</strong>, give it a name, and copy it. It starts with <code>gsk_</code>.
          </li>
          <li>
            In DocTune, open{' '}
            <Link to="/settings" className="underline">
              Settings
            </Link>
            , paste the key under Groq and save. DocTune checks that it works.
          </li>
        </ol>
        <p>
          Free keys have daily limits. When one runs out, DocTune waits for it to reset and carries on by itself, so big datasets can take a day or
          more.
        </p>
      </>
    ),
  },
  {
    slug: 'gemini-key',
    title: 'Add a Gemini key to go faster',
    summary: 'A second free key gives you more daily quota.',
    body: (
      <>
        <ol>
          <li>Open {ext('https://aistudio.google.com/apikey', 'Google AI Studio')} and create an API key.</li>
          <li>
            Paste it under Gemini in{' '}
            <Link to="/settings" className="underline">
              Settings
            </Link>
            .
          </li>
          <li>Tick the box to confirm you understand Google&apos;s terms: they restrict using Gemini output to build competing models.</li>
        </ol>
        <p>Gemini is not available in some EU and UK regions. If your key is refused, keep using Groq alone.</p>
      </>
    ),
  },
  {
    slug: 'run-notebook',
    title: 'Run the notebook and resume after a pause',
    summary: 'Training runs on a free GPU in your own Google Colab.',
    body: (
      <>
        <h2>First run</h2>
        <ol>
          <li>Set up training in your project. DocTune shows a job token once. Copy it.</li>
          <li>
            Choose <strong>Open in Colab</strong> and sign in with your Google account.
          </li>
          <li>
            Choose <strong>Runtime → Change runtime type → T4 GPU</strong>.
          </li>
          <li>
            Choose <strong>Runtime → Run all</strong>, paste the token when asked, and keep the tab open.
          </li>
        </ol>
        <h2>If it pauses</h2>
        <p>
          Free Colab can end a session at any time: after about 12 hours, when the tab sits idle, or when no free GPU is left. This is normal. DocTune
          saves a checkpoint every few minutes, so progress is kept.
        </p>
        <p>
          To continue, open the notebook again and run all cells with the same token. If you lost the token, make a new one on the project page.
          Training picks up from the last checkpoint.
        </p>
      </>
    ),
  },
  {
    slug: 'ollama',
    title: 'Use your GGUF in Ollama',
    summary: 'Run your model on your own computer.',
    body: (
      <>
        <ol>
          <li>Find the GGUF file in the Google Drive folder the notebook told you about, and download it.</li>
          <li>
            Next to it, create a file named <code>Modelfile</code> containing one line: <code>FROM ./model-q4_k_m.gguf</code> (use your real file
            name).
          </li>
          <li>
            Install {ext('https://ollama.com', 'Ollama')}, then run <code>ollama create my-doctune-model -f Modelfile</code> and{' '}
            <code>ollama run my-doctune-model</code>.
          </li>
        </ol>
        <p>Running locally is much faster than the shared playground, and your questions never leave your computer.</p>
      </>
    ),
  },
  {
    slug: 'why-finetune-rag',
    title: 'Why fine-tuning and RAG together',
    summary: 'Fine-tuning teaches style. Your documents supply the facts.',
    body: (
      <>
        <p>
          <strong>Fine-tuning</strong> changes how a model answers: tone, length, format. It is not a reliable way to store facts.
        </p>
        <p>
          <strong>RAG</strong> (retrieval) looks up the right passages from your documents for each question and hands them to the model. That is
          where the facts come from.
        </p>
        <p>
          The playground uses both: your tuned model for the style, and your documents for the content. Turn &quot;Use my documents&quot; off to see
          what the fine-tuning alone does.
        </p>
      </>
    ),
  },
]

export function findDoc(slug: string | undefined): DocPage | undefined {
  return DOCS.find((d) => d.slug === slug)
}
