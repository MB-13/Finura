import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ReviewTable } from '@/features/dataset/ReviewTable'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { makePair, makeProject, makeStyle, type PairOut } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const PAIRS: PairOut[] = [
  makePair({ id: 'p1', question: 'First question?', answer: 'First answer.' }),
  makePair({ id: 'p2', question: 'Second question?', answer: 'Second answer.', split: 'eval', origin: 'user_added', edited: true }),
  makePair({ id: 'p3', question: 'Third question?', answer: 'Third answer.', kept: false, dropped_reason: 'low_score' }),
]

const listPairs =
  (pairs: PairOut[] = PAIRS): Handler =>
  (url, req) =>
    url.pathname.endsWith('/pairs') && req.method === 'GET' ? jsonResponse({ items: pairs, next_cursor: null }) : undefined

const inReview = makeProject({ status: 'in_review' })
const row = (n: number) => document.querySelector<HTMLElement>(`[data-row-index="${n}"]`)!

describe('ReviewTable', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists pairs with split, origin, edited and dropped badges', async () => {
    stubApi(listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    expect(await screen.findByText('First question?')).toBeInTheDocument()
    expect(screen.getByText('Added by you')).toBeInTheDocument()
    expect(screen.getByText('Edited')).toBeInTheDocument()
    expect(screen.getByText('Dropped: low score')).toBeInTheDocument()
    expect(screen.getAllByText('Setup > Reset').length).toBeGreaterThan(0)
  })

  it('sends filters, debounced search and sort to the API', async () => {
    const calls = stubApi(listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await screen.findByText('First question?')
    await userEvent.selectOptions(screen.getByLabelText('Split'), 'eval')
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'dropped')
    await userEvent.selectOptions(screen.getByLabelText('Sort'), '-score')
    await userEvent.type(screen.getByLabelText('Search'), 'reset')
    await waitFor(() =>
      expect(
        calls.some((c) => {
          const p = c.url.searchParams
          return p.get('split') === 'eval' && p.get('kept') === 'false' && p.get('sort') === '-score' && p.get('q') === 'reset' && p.get('limit') === '100'
        }),
      ).toBe(true),
    )
    // typing alone must not fire a request per keystroke
    expect(calls.filter((c) => c.url.searchParams.get('q') === 'r')).toHaveLength(0)
  })

  it('shows an empty state for filters with no results', async () => {
    stubApi(listPairs([]))
    renderRoutes(<ReviewTable project={inReview} />)
    expect(await screen.findByText('No pairs yet')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Search'), 'zebra')
    expect(await screen.findByText('No pairs match these filters')).toBeInTheDocument()
  })

  it('shows an error state with retry', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Pairs unavailable' }, 400))
    renderRoutes(<ReviewTable project={inReview} />)
    expect(await screen.findByText('Pairs unavailable')).toBeInTheDocument()
  })

  it('loads more with the opaque cursor', async () => {
    const calls = stubApi((url) => {
      if (!url.pathname.endsWith('/pairs')) return undefined
      return url.searchParams.get('cursor') === 'abc'
        ? jsonResponse({ items: [makePair({ id: 'p9', question: 'Ninth question?' })], next_cursor: null })
        : jsonResponse({ items: [PAIRS[0]], next_cursor: 'abc' })
    })
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Ninth question?')).toBeInTheDocument()
    expect(calls.some((c) => c.url.searchParams.get('cursor') === 'abc')).toBe(true)
  })

  it('edits a pair and saves it with PATCH', async () => {
    const calls = stubApi(
      (_url, req) => (req.method === 'PATCH' ? jsonResponse({ ...PAIRS[0], question: 'Reworded?', edited: true }) : undefined),
      listPairs(),
    )
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Edit pair 1' }))
    const q = screen.getByLabelText('Question for pair 1')
    await userEvent.clear(q)
    await userEvent.type(q, 'Reworded?')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(patch.url.pathname.endsWith('/pairs/p1')).toBe(true)
    expect(await patch.request.json()).toEqual({ record: { format: 'qa_chat', question: 'Reworded?', answer: 'First answer.' } })
  })

  it('edits a whole conversation, adding and removing follow-ups', async () => {
    const conversation = makePair({
      id: 'c1',
      dataset_format: 'multi_turn',
      question: 'What is it?',
      answer: 'More detail.',
      record: {
        format: 'multi_turn',
        messages: [
          { role: 'user', content: 'What is it?' },
          { role: 'assistant', content: 'A device.' },
          { role: 'user', content: 'Tell me more?' },
          { role: 'assistant', content: 'More detail.' },
        ],
      },
    })
    const calls = stubApi((_url, req) => (req.method === 'PATCH' ? jsonResponse(conversation) : undefined), listPairs([conversation]))
    const project = makeProject({ status: 'in_review', style: makeStyle({ dataset_format: 'multi_turn' }) })
    renderRoutes(<ReviewTable project={project} />)
    expect(await screen.findByText('+ 1 follow-up')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toContain('Opening question')

    await userEvent.click(screen.getByRole('button', { name: 'Edit pair 1' }))
    await userEvent.click(screen.getByRole('button', { name: /Add a follow-up/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fill in every turn')
    await userEvent.click(screen.getByRole('button', { name: /Remove the last follow-up/ }))
    const second = screen.getByLabelText('Assistant turn 2 for conversation 1')
    await userEvent.clear(second)
    await userEvent.type(second, 'Even more.')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    const body = (await calls.find((c) => c.method === 'PATCH')!.request.json()) as { record: { messages: { content: string }[] } }
    expect(body.record.messages.map((m) => m.content)).toEqual(['What is it?', 'A device.', 'Tell me more?', 'Even more.'])
  })

  it('drops a pair optimistically and rolls back when the request fails', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    let patched = false
    stubApi(
      (_url, req) => {
        if (req.method !== 'PATCH') return undefined
        patched = true
        return gate.then(() => jsonResponse({ error: 'boom', message: 'Server said no' }, 500))
      },
      // after the PATCH the refetch never answers, so only the rollback can restore the row
      (_url, req) => (patched && req.method === 'GET' ? new Promise<Response>(() => {}) : undefined),
      listPairs(),
    )
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Drop pair 1' }))
    // optimistic: flips to Restore before the server answers
    expect(await screen.findByRole('button', { name: 'Restore pair 1' })).toBeInTheDocument()
    release()
    expect(await screen.findByRole('button', { name: 'Drop pair 1' })).toBeInTheDocument()
  })

  it('moves a pair to the other split', async () => {
    const calls = stubApi((_url, req) => (req.method === 'PATCH' ? jsonResponse({ ...PAIRS[0], split: 'eval' }) : undefined), listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Move pair 1 to eval' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    expect(await calls.find((c) => c.method === 'PATCH')!.request.json()).toEqual({ split: 'eval' })
  })

  it('runs bulk actions on the selected pairs', async () => {
    const calls = stubApi((url, req) => (url.pathname.endsWith('/pairs/bulk') && req.method === 'POST' ? jsonResponse({ updated: 2 }) : undefined), listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Select pair 1' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select pair 2' }))
    const bar = screen.getByRole('toolbar', { name: 'Bulk actions' })
    expect(within(bar).getByText('2 selected')).toBeInTheDocument()
    await userEvent.click(within(bar).getByRole('button', { name: 'Drop' }))
    await waitFor(() => expect(calls.some((c) => c.url.pathname.endsWith('/pairs/bulk'))).toBe(true))
    expect(await calls.find((c) => c.url.pathname.endsWith('/pairs/bulk'))!.request.json()).toEqual({ ids: ['p1', 'p2'], action: 'drop' })
    await waitFor(() => expect(screen.queryByRole('toolbar', { name: 'Bulk actions' })).not.toBeInTheDocument())
  })

  it('adds a pair through the dialog', async () => {
    const calls = stubApi((url, req) => (url.pathname.endsWith('/pairs') && req.method === 'POST' ? jsonResponse(makePair({ id: 'new' })) : undefined), listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('button', { name: /Add pair/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Question'), 'New q?')
    await userEvent.type(within(dialog).getByLabelText('Answer'), 'New a.')
    await userEvent.selectOptions(within(dialog).getByLabelText('Use for'), 'eval')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add pair' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(await calls.find((c) => c.method === 'POST')!.request.json()).toEqual({
      record: { format: 'qa_chat', question: 'New q?', answer: 'New a.' },
      split: 'eval',
    })
  })

  it('adds an instruction example with optional input text', async () => {
    const calls = stubApi((url, req) => (url.pathname.endsWith('/pairs') && req.method === 'POST' ? jsonResponse(makePair({ id: 'new' })) : undefined), listPairs([]))
    const project = makeProject({ status: 'in_review', style: makeStyle({ dataset_format: 'instruction' }) })
    renderRoutes(<ReviewTable project={project} />)
    await userEvent.click(await screen.findByRole('button', { name: /Add pair/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Instruction'), 'Summarize this.')
    await userEvent.type(within(dialog).getByLabelText('Output'), 'Short.')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add pair' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(await calls.find((c) => c.method === 'POST')!.request.json()).toEqual({
      record: { format: 'instruction', instruction: 'Summarize this.', input: '', output: 'Short.' },
      split: 'train',
    })
  })

  it('supports keyboard shortcuts but not while typing', { timeout: 15_000 }, async () => {
    const calls = stubApi((_url, req) => (req.method === 'PATCH' ? jsonResponse({ ...PAIRS[1] }) : undefined), listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await screen.findByText('First question?')
    await userEvent.type(screen.getByLabelText('Search'), 'd')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
    // typing re-queries the list; let that finish so the rows don't re-render under the keyboard focus
    await waitFor(() => expect(calls.some((c) => c.url.searchParams.get('q') === 'd')).toBe(true))
    await screen.findByText('First question?')
    await userEvent.click(document.body)
    await userEvent.keyboard('j')
    expect(document.activeElement).toBe(row(1))
    await userEvent.keyboard('d')
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.url.pathname.endsWith('/pairs/p2'))).toBe(true))
    expect(await calls.find((c) => c.method === 'PATCH')!.request.json()).toEqual({ kept: false })
    await userEvent.keyboard('j')
    await userEvent.keyboard('r')
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH').length).toBe(2))
    expect(await calls.filter((c) => c.method === 'PATCH')[1]!.request.json()).toEqual({ kept: true })
    await userEvent.keyboard('k')
    await userEvent.keyboard('e')
    expect(await screen.findByLabelText('Question for pair 2')).toBeInTheDocument()
  })

  it('ignores shortcuts while a menu is open', async () => {
    const calls = stubApi((_url, req) => (req.method === 'PATCH' ? jsonResponse({ ...PAIRS[0] }) : undefined), listPairs())
    renderRoutes(
      <>
        <DropdownMenu>
          <DropdownMenuTrigger>Account menu</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>Settings</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <ReviewTable project={inReview} />
      </>,
    )
    await screen.findByText('First question?')
    await userEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    const item = await screen.findByRole('menuitem', { name: 'Settings' })
    item.focus()
    // "d" would drop the focused pair if the menu did not own the keyboard
    await userEvent.keyboard('d')
    await userEvent.keyboard('j')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
    expect(document.querySelector('[data-row-index="1"]')).not.toBe(document.activeElement)
  })

  it('keeps the bulk actions bar before the table so it can stick above it', async () => {
    stubApi(listPairs())
    renderRoutes(<ReviewTable project={inReview} />)
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Select pair 1' }))
    const bar = screen.getByRole('toolbar', { name: 'Bulk actions' })
    const table = screen.getByRole('table', { name: 'Dataset pairs' })
    expect(bar.parentElement).toBe(table.parentElement)
    expect(bar.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('is read-only when the project is not in review', async () => {
    stubApi(listPairs())
    renderRoutes(<ReviewTable project={makeProject({ status: 'awaiting_run' })} />)
    expect(await screen.findByText('First question?')).toBeInTheDocument()
    expect(screen.getByText(/read-only/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add pair/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Drop pair 1' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Select pair 1' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'View pair 1' }))
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })
})
