import { vi } from 'vitest'

export class MockXHR {
  static instances: MockXHR[] = []
  method = ''
  url = ''
  headers: Record<string, string> = {}
  body: unknown = null
  status = 200
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  constructor() {
    MockXHR.instances.push(this)
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  send(body: unknown) {
    this.body = body
    queueMicrotask(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 })
      this.onload?.()
    })
  }
  abort() {
    this.onabort?.()
  }
}

export function stubXhr() {
  MockXHR.instances = []
  vi.stubGlobal('XMLHttpRequest', MockXHR)
  return MockXHR.instances
}
