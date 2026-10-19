import type { components } from '@/lib/api/schema'

export type DocumentWithChunks = components['schemas']['DocumentWithChunks']
export type SignedUpload = components['schemas']['SignedUrlOut']

export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown'] as const
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')
const MB = 1024 * 1024

export function formatMb(bytes: number): string {
  return (bytes / MB).toFixed(1)
}

export type Limits = { file_mb: number; project_mb: number }

/** Client-side pre-check. Returns a user-facing message, or null when the file may be uploaded. */
export function validateFile(file: { name: string; size: number }, limits: Limits, usedBytes: number): string | null {
  const lower = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `${file.name}: unsupported file type. Use PDF, DOCX, TXT or Markdown.`
  }
  if (file.size === 0) return `${file.name}: the file is empty.`
  if (file.size > limits.file_mb * MB) {
    return `${file.name}: larger than the ${limits.file_mb} MB per-file limit.`
  }
  if (usedBytes + file.size > limits.project_mb * MB) {
    return `${file.name}: would exceed the ${limits.project_mb} MB project limit.`
  }
  return null
}

/** PUT the file to a pre-signed URL with progress. Never sends the Authorization header. */
export function putToSignedUrl(
  upload: Pick<SignedUpload, 'url' | 'method' | 'headers'>,
  file: Blob,
  onProgress: (percent: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open(upload.method, upload.url)
    for (const [name, value] of Object.entries(upload.headers)) xhr.setRequestHeader(name, value)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100)
        resolve()
      } else {
        reject(new Error(`Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.onabort = () => reject(new Error('Upload cancelled'))
    signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(file)
  })
}
