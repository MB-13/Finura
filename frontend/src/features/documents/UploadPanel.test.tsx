import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { UploadPanel } from '@/features/documents/UploadPanel'
import { jsonResponse, META, stubApi } from '@/test/api'
import { makeDocument, makeProject, PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'
import { MockXHR, stubXhr } from '@/test/xhr'

const project = makeProject({ status: 'uploaded', allowed_actions: ['upload', 'remove_document', 'process', 'rename', 'delete'], total_bytes: 12.3 * 1024 * 1024 })
const docsPath = `/projects/${PROJECT_ID}/documents`

function baseHandlers(documents = [makeDocument()]) {
  return [
    (url: URL) => (url.pathname === '/meta' ? jsonResponse(META) : undefined),
    (url: URL, req: Request) => (url.pathname === docsPath && req.method === 'GET' ? jsonResponse(documents) : undefined),
    (url: URL) => (url.pathname === `/projects/${PROJECT_ID}` ? jsonResponse(project) : undefined),
  ]
}

function fileOf(name: string, size: number, type = 'application/pdf') {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('UploadPanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the size meter, file list and a Process button only when allowed', async () => {
    stubApi(...baseHandlers())
    const { unmount } = renderRoutes(<UploadPanel project={project} />)
    expect(await screen.findByText('notes.pdf')).toBeInTheDocument()
    expect(screen.getByText('12.3 / 50 MB')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Process documents' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Remove notes.pdf' })).toBeInTheDocument()
    unmount()

    renderRoutes(<UploadPanel project={{ ...project, allowed_actions: [] }} />)
    await screen.findByText('notes.pdf')
    expect(screen.queryByRole('button', { name: 'Process documents' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove notes.pdf' })).not.toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    stubApi(...baseHandlers([]))
    renderRoutes(<UploadPanel project={project} />)
    expect(await screen.findByText(/No documents yet/)).toBeInTheDocument()
  })

  it('rejects .exe and files over 20 MB without calling the API', async () => {
    const calls = stubApi(...baseHandlers())
    renderRoutes(<UploadPanel project={project} />)
    await screen.findByText('notes.pdf')
    const input = screen.getByLabelText(/Drop files here/) as HTMLInputElement
    await userEvent.upload(input, [fileOf('virus.exe', 100, 'application/octet-stream'), fileOf('big.pdf', 21 * 1024 * 1024)], {
      applyAccept: false,
    })
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/virus\.exe: unsupported file type/)).toBeInTheDocument()
    expect(within(alert).getByText(/big\.pdf: larger than the 20 MB per-file limit/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('uploads: create -> PUT to the signed URL without Authorization -> complete', async () => {
    const instances = stubXhr()
    const doc = makeDocument({ id: 'new-doc', filename: 'new.pdf', status: 'pending_upload' })
    const calls = stubApi(
      (url, req) =>
        url.pathname === docsPath && req.method === 'POST'
          ? jsonResponse(
              {
                document: doc,
                upload: { url: 'https://r2.example/put?sig=1', method: 'PUT', headers: { 'Content-Type': 'application/pdf' }, expires_at: 1 },
              },
              201,
            )
          : undefined,
      (url, req) =>
        url.pathname === `${docsPath}/new-doc/complete` && req.method === 'POST' ? jsonResponse({ ...doc, status: 'uploaded' }) : undefined,
      ...baseHandlers(),
    )
    renderRoutes(<UploadPanel project={project} />)
    await screen.findByText('notes.pdf')
    await userEvent.upload(screen.getByLabelText(/Drop files here/), fileOf('new.pdf', 1000))

    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/new-doc/complete'))).toBe(true))
    const order = calls.filter((c) => c.method === 'POST').map((c) => c.url.pathname)
    expect(order).toEqual([docsPath, `${docsPath}/new-doc/complete`])
    const create = calls.find((c) => c.method === 'POST')!
    expect(await create.request.json()).toEqual({ filename: 'new.pdf', size_bytes: 1000 })

    expect(instances).toHaveLength(1)
    expect(instances[0]!.url).toBe('https://r2.example/put?sig=1')
    expect(instances[0]!.method).toBe('PUT')
    expect(Object.keys(instances[0]!.headers).map((h) => h.toLowerCase())).not.toContain('authorization')
    expect(instances[0]).toBeInstanceOf(MockXHR)
  })

  it('shows the server error inline when an upload is refused', async () => {
    stubXhr()
    stubApi(
      (url, req) =>
        url.pathname === docsPath && req.method === 'POST'
          ? jsonResponse({ error: 'limit_exceeded', message: 'Project is over 50 MB' }, 413)
          : undefined,
      ...baseHandlers(),
    )
    renderRoutes(<UploadPanel project={project} />)
    await screen.findByText('notes.pdf')
    await userEvent.upload(screen.getByLabelText(/Drop files here/), fileOf('new.pdf', 1000))
    expect(await screen.findByText('Project is over 50 MB')).toBeInTheDocument()
  })

  it('calls process when the button is pressed', async () => {
    const calls = stubApi(
      (url, req) =>
        url.pathname === `/projects/${PROJECT_ID}/process` && req.method === 'POST'
          ? jsonResponse({ ...project, status: 'parsing' }, 202)
          : undefined,
      ...baseHandlers(),
    )
    renderRoutes(<UploadPanel project={project} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Process documents' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/process'))).toBe(true))
  })
})
