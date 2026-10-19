import { putToSignedUrl, validateFile } from '@/features/documents/upload'
import { MockXHR, stubXhr } from '@/test/xhr'

const limits = { file_mb: 20, project_mb: 50 }
const MB = 1024 * 1024

describe('validateFile', () => {
  it('accepts supported types', () => {
    for (const name of ['a.pdf', 'a.DOCX', 'a.txt', 'a.md', 'a.markdown']) {
      expect(validateFile({ name, size: 10 }, limits, 0)).toBeNull()
    }
  })
  it('rejects unsupported types, empty, oversize and project overflow', () => {
    expect(validateFile({ name: 'x.exe', size: 10 }, limits, 0)).toMatch(/unsupported file type/)
    expect(validateFile({ name: 'a.pdf', size: 0 }, limits, 0)).toMatch(/empty/)
    expect(validateFile({ name: 'a.pdf', size: 21 * MB }, limits, 0)).toMatch(/20 MB per-file/)
    expect(validateFile({ name: 'a.pdf', size: 15 * MB }, limits, 40 * MB)).toMatch(/50 MB project/)
  })
})

describe('putToSignedUrl', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('PUTs with the signed headers only and reports progress', async () => {
    stubXhr()
    const progress: number[] = []
    await putToSignedUrl(
      { url: 'https://r2.example/put?sig=1', method: 'PUT', headers: { 'Content-Type': 'application/pdf' } },
      new Blob(['x']),
      (p) => progress.push(p),
    )
    const xhr = MockXHR.instances[0]!
    expect(xhr.method).toBe('PUT')
    expect(xhr.url).toBe('https://r2.example/put?sig=1')
    expect(xhr.headers).toEqual({ 'Content-Type': 'application/pdf' })
    expect(progress).toEqual([50, 100])
  })
  it('rejects on a non-2xx status', async () => {
    stubXhr()
    const original = MockXHR.prototype.send
    MockXHR.prototype.send = function (this: MockXHR, body: unknown) {
      this.status = 403
      original.call(this, body)
    }
    try {
      await expect(putToSignedUrl({ url: 'u', method: 'PUT', headers: {} }, new Blob(['x']), () => {})).rejects.toThrow(/403/)
    } finally {
      MockXHR.prototype.send = original
    }
  })
})
