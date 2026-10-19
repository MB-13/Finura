import { LegalPage } from '@/features/marketing/LegalPage'

export function Privacy() {
  return (
    <LegalPage title="Privacy" updated="October 2026 (draft)">
      <p>DocTune turns your documents into a fine-tuned model. This page explains, in plain language, what happens to your data.</p>

      <h2>Your documents go to AI providers you choose</h2>
      <p>
        To write your training data, DocTune sends parts of your documents to the third-party AI providers whose API keys you connect (for example Groq or
        Google Gemini). Those providers process them under their own terms and privacy policies. If you do not want a provider to see your documents, do not
        connect that provider&apos;s key.
      </p>

      <h2>What DocTune stores</h2>
      <ul>
        <li>Your account details (email and name).</li>
        <li>The files you upload, the text we extract from them, and the training data we generate.</li>
        <li>Your provider API keys, stored encrypted and never shown again in full.</li>
        <li>Training job records and the files a job produces (the adapter and the latest checkpoint).</li>
      </ul>
      <p>DocTune never stores your Google credentials or Hugging Face tokens. You type those into the notebook yourself.</p>

      <h2>How long we keep job files</h2>
      <p>Job files, such as checkpoints and adapters, are deleted 14 days after a job ends.</p>

      <h2>Training happens in your Google account</h2>
      <p>
        Training runs in your own Google Colab account, under Google&apos;s terms and privacy policy. The notebook downloads your dataset and sends progress back
        to DocTune with a one-job token.
      </p>

      <h2>Deleting your data</h2>
      <p>You can delete your account and all of your data at any time from Settings. Deletion starts right away and finishes in the background.</p>

      <h2>Contact</h2>
      <p>Contact details will be added before launch.</p>
    </LegalPage>
  )
}
