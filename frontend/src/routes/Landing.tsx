import { ArrowRight, Clock, Cpu, FileUp, Palette, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Callout } from '@/components/Callout'
import { GuideJoint, GuideRails } from '@/components/marketing/GuideRails'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/auth-context'
import { FeatureBento } from '@/features/marketing/FeatureBento'
import { HeroVisual } from '@/features/marketing/HeroVisual'
import { StepShowcase } from '@/features/marketing/StepShowcase'

const expectations: { title: string; text: string }[] = [
  {
    title: 'Fine-tuning teaches style',
    text: 'Your model learns how to answer: tone, length and format. It is not a reliable way to store facts.',
  },
  {
    title: 'Your documents supply the facts',
    text: 'In the playground, the model looks up the right passages from your files for each question (this is called RAG).',
  },
  {
    title: 'Free means your own free accounts',
    text: 'You bring a free AI provider key and a free GPU. DocTune does not charge you, and free tiers have limits.',
  },
]

const faqs = [
  {
    q: 'Is it really free?',
    a: 'Yes. You use your own free AI provider key to write the training data and your own free Kaggle or Google Colab GPU to train. DocTune does not charge you.',
  },
  {
    q: 'Fine-tuning or RAG: which one do I need?',
    a: 'Both help in different ways. Fine-tuning teaches your model how to answer (tone, length, format). RAG looks up facts from your documents while it answers. The playground uses both.',
  },
  {
    q: 'What happens when Colab pauses?',
    a: 'Free Colab sessions can end at any time. DocTune saves checkpoints every few minutes, so you open the notebook again and training continues from where it stopped.',
  },
  {
    q: 'Which models can I train?',
    a: 'Small open models, such as Qwen. Each model card shows its size, its license and whether it fits a free T4 GPU, so you can choose without guessing.',
  },
  {
    q: 'Where do my documents go?',
    a: 'Parts of them are sent to the AI providers whose keys you connect, to write training examples. You can delete your account and all your data at any time.',
  },
]

const rails = 'max-sm:border-x-0'

function Chip({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <span className="mx-0.5 inline-flex items-center gap-1.5 rounded-md border bg-card px-2 py-0.5 align-baseline text-[0.85em] font-medium text-foreground shadow-xs">
      <Icon className="size-[0.9em] text-muted-foreground" aria-hidden />
      {children}
    </span>
  )
}

function SectionHeading({ id, eyebrow, title, description }: { id: string; eyebrow: string; title: string; description?: string }) {
  return (
    <div className="flex max-w-2xl flex-col gap-3">
      <div className="text-eyebrow">{eyebrow}</div>
      <h2 id={id} className="text-3xl leading-[2.25rem] font-[650] tracking-[-0.03em] text-balance sm:text-4xl sm:leading-[2.75rem]">
        {title}
      </h2>
      {description && <p className="text-lg leading-7 text-muted-foreground">{description}</p>}
    </div>
  )
}

export function Landing() {
  const { session } = useAuth()
  const cta = session ? '/projects' : '/sign-in'
  const ctaLabel = session ? 'Open your projects' : 'Get started free'
  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-glow" />
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-grid" />
        <GuideRails className={rails}>
          <div className="relative flex flex-col items-center gap-6 px-4 pt-14 text-center sm:px-6 sm:pt-20">
            <span className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-caption font-medium text-muted-foreground shadow-xs">
              <span className="size-1.5 rounded-full bg-success" aria-hidden /> Free to use. Open-source models.
            </span>
            <h1 className="text-display max-w-4xl">
              Turn your documents into <span className="text-muted-foreground">your own AI model</span>
            </h1>
            <p className="max-w-2xl text-base leading-8 text-muted-foreground sm:text-xl sm:leading-9">
              Upload your <Chip icon={FileUp}>documents</Chip>, describe the <Chip icon={Palette}>style</Chip> you want, and train on a{' '}
              <Chip icon={Cpu}>free GPU</Chip> in your own account. No ML knowledge needed.
            </p>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
              <Button asChild size="lg" className="max-sm:w-full">
                <Link to={cta}>
                  {ctaLabel} <ArrowRight aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="max-sm:w-full">
                <a href="#how-it-works">See how it works</a>
              </Button>
            </div>
            <p className="text-caption text-muted-foreground">No card needed. You bring a free AI key and a free GPU.</p>
          </div>
          <div className="relative mt-12 px-4 sm:mt-16 sm:px-6">
            <HeroVisual />
          </div>
        </GuideRails>
      </section>
      <GuideJoint />

      {/* Statement */}
      <GuideRails className={rails}>
        <p className="mx-auto max-w-3xl px-4 py-16 text-center text-2xl leading-9 font-medium tracking-tight text-muted-foreground sm:px-6 sm:py-24 sm:text-3xl sm:leading-[2.75rem]">
          <span className="text-foreground">Fine-tuning teaches your model how to answer.</span> Your documents supply the facts, looked up live in
          the playground, so it sounds like you and stays grounded in what you wrote.
        </p>
      </GuideRails>
      <GuideJoint />

      {/* How it works */}
      <GuideRails className={rails}>
        <section id="how-it-works" aria-labelledby="how-title" className="flex scroll-mt-24 flex-col gap-10 px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading
            id="how-title"
            eyebrow="How it works"
            title="From documents to a model in five steps"
            description="DocTune always tells you what to do next, and you can stop and come back at any step."
          />
          <StepShowcase />
        </section>
      </GuideRails>
      <GuideJoint />

      {/* Features */}
      <GuideRails className={rails}>
        <section aria-labelledby="features-title" className="flex flex-col gap-10 px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading id="features-title" eyebrow="Features" title="Built for people who aren't ML experts" />
          <FeatureBento />
        </section>
      </GuideRails>
      <GuideJoint />

      {/* Honest expectations */}
      <GuideRails className={rails}>
        <section aria-labelledby="expect-title" className="flex flex-col gap-10 px-4 py-16 sm:px-6 sm:py-20">
          <SectionHeading
            id="expect-title"
            eyebrow="Honest expectations"
            title="What you will and won't get"
            description="So nothing surprises you later."
          />
          <ul className="grid gap-8 md:grid-cols-3 md:gap-0 md:divide-x">
            {expectations.map((e, i) => (
              <li key={e.title} className="flex flex-col gap-3 md:px-8 md:first:pl-0 md:last:pr-0">
                <span className="text-metric text-xs text-muted-foreground">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="text-section-title">{e.title}</h3>
                <p className="text-body text-muted-foreground">{e.text}</p>
              </li>
            ))}
          </ul>
          <Callout tone="info" icon={Clock} title="Plan for patience">
            Writing the training data can take a day or more on free keys, and training takes about an hour. DocTune keeps your progress, so you can
            close the tab and return.
          </Callout>
        </section>
      </GuideRails>
      <GuideJoint />

      {/* FAQ */}
      <GuideRails className={rails}>
        <section
          id="faq"
          aria-labelledby="faq-title"
          className="grid scroll-mt-24 gap-8 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[1fr_2fr] lg:gap-16"
        >
          <div className="flex flex-col gap-3">
            <div className="text-eyebrow">FAQ</div>
            <h2 id="faq-title" className="text-page-title">
              Questions
            </h2>
            <p className="text-body text-muted-foreground">
              More in the{' '}
              <Link to="/docs" className="font-medium text-primary underline underline-offset-4">
                help guides
              </Link>
              .
            </p>
          </div>
          <div className="divide-y border-y">
            {faqs.map((f) => (
              <details key={f.q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-sm text-card-title focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <span
                    aria-hidden
                    className="text-lg leading-none text-muted-foreground transition-transform group-open:rotate-45 motion-reduce:transition-none"
                  >
                    +
                  </span>
                </summary>
                <p className="mt-2 max-w-[65ch] text-sm text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </div>
        </section>
      </GuideRails>
      <GuideJoint />

      {/* Closing CTA */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-glow" />
        <GuideRails className={rails}>
          <div className="relative flex flex-col items-center gap-6 px-4 py-20 text-center sm:px-6 sm:py-28">
            <h2 className="text-display-sm max-w-2xl">Ready to teach a model your way of answering?</h2>
            <p className="max-w-lg text-lg leading-7 text-muted-foreground">
              Start with one project. It takes a few minutes to set up, and you can pause any time.
            </p>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
              <Button asChild size="lg" className="max-sm:w-full">
                <Link to={cta}>
                  {ctaLabel} <ArrowRight aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="ghost" className="max-sm:w-full">
                <Link to="/docs">Read the help guides</Link>
              </Button>
            </div>
          </div>
        </GuideRails>
      </section>
    </div>
  )
}
