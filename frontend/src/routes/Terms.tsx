import { LegalPage } from '@/features/marketing/LegalPage'

export function Terms() {
  return (
    <LegalPage title="Terms of use" updated="October 2026 (draft)">
      <p>These are the plain-language terms for using DocTune.</p>

      <h2>What DocTune does</h2>
      <p>
        DocTune helps you turn your own documents into training data and fine-tune an open-source model. Training runs in your own Google Colab account, under
        Google&apos;s terms. DocTune does not run anything in your account.
      </p>

      <h2>Your responsibilities</h2>
      <ul>
        <li>You must have the right to use the documents you upload.</li>
        <li>You are responsible for following the terms of the AI providers whose keys you connect, including any limits on how their output may be used.</li>
        <li>You are responsible for following the license of the base model you choose, including notices such as &quot;Built with Llama&quot;.</li>
        <li>You are responsible for following Google Colab&apos;s rules while you run the notebook.</li>
      </ul>

      <h2>Files and your account</h2>
      <p>
        DocTune stores your files and job artifacts. Job files are deleted 14 days after a job ends. You can delete your account and all of your data at any
        time from Settings.
      </p>

      <h2>No warranty</h2>
      <p>
        DocTune is provided as is, without any warranty. Free services change: provider quotas, Colab GPU availability and model licenses can change without
        notice, and models can give wrong answers. Check anything important before you rely on it.
      </p>

      <h2>Contact</h2>
      <p>Contact details will be added before launch.</p>
    </LegalPage>
  )
}
