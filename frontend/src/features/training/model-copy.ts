import type { BaseModel, ModelCheck } from '@/features/training/api'

export const MODE_LABEL: Record<BaseModel['train_mode'], string> = {
  lora16: 'Standard (16-bit)',
  qlora4: 'Memory-saving (4-bit)',
}

export const WARNING_COPY: Record<string, string> = {
  license_review: "This model's license needs a quick read. Make sure it allows what you plan to do with the result.",
  gated_requires_token: "This model is gated, so you'll need your own Hugging Face token in the notebook.",
  may_not_fit: 'This model may not fit on the free T4 GPU. Training could fail or run out of memory.',
  size_unknown: "We couldn't read the model's size, so we can't tell if it fits on a free GPU.",
}

export const BLOCKING_COPY: Record<string, string> = {
  invalid_id: "That doesn't look like a Hugging Face model id. It should look like organisation/model-name.",
  not_found: "We couldn't find that model on Hugging Face. Check the spelling.",
  unsupported_architecture: "This kind of model isn't supported by our training setup yet. Pick another one.",
  too_large: 'This model is too big for a free Colab GPU (about 10 billion parameters is the limit).',
}

export const FITS_COPY: Record<ModelCheck['fits_t4'], string> = {
  yes: 'Fits the free T4',
  maybe: 'May not fit the free T4',
  no: "Won't fit the free T4",
}

export const CREATE_ERRORS: Record<string, string> = {
  invalid_state: 'This project is not ready for training. Refresh the page and try again.',
  dataset_not_approved: 'Approve your dataset first.',
  model_blocked: "That model can't be used for training. Pick a different one.",
  kaggle_not_connected: 'Kaggle is not connected. Connect it in Settings, or choose Google Colab.',
  kaggle_gated_model: 'This model needs a Hugging Face token. Use Google Colab for it instead.',
  license_ack_required: "Please confirm you've read the model's license.",
}

export function blockingMessage(code: string): string {
  return BLOCKING_COPY[code] ?? `This model can't be used (${code.replace(/_/g, ' ')}).`
}

export function warningMessage(code: string): string {
  return WARNING_COPY[code] ?? code.replace(/_/g, ' ')
}
