import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ProjectHeader } from '@/features/projects/ProjectHeader'
import { jsonResponse, stubApi } from '@/test/api'
import { makeProject } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const project = makeProject({ name: 'Support answers', status: 'draft', allowed_actions: ['rename', 'delete'] })

describe('ProjectHeader', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the h1, status badge and hint while renaming', async () => {
    stubApi()
    renderRoutes(<ProjectHeader project={project} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Support answers' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    expect(screen.getByRole('textbox', { name: 'Project name' })).toHaveFocus()
    expect(screen.getByRole('heading', { level: 1, name: 'Support answers' })).toBeInTheDocument()
    expect(screen.getByText('Add the documents your model should learn from.')).toBeInTheDocument()
    expect(screen.getByText('Draft')).toBeInTheDocument()
  })

  it('returns focus to the Rename button on Cancel, Escape and Save', async () => {
    const calls = stubApi((_url, req) => (req.method === 'PATCH' ? jsonResponse({ ...project, name: 'New name' }) : undefined))
    renderRoutes(<ProjectHeader project={project} />)

    await userEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Rename project' })).toHaveFocus()

    await userEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    await userEvent.keyboard('{Escape}')
    expect(screen.getByRole('button', { name: 'Rename project' })).toHaveFocus()

    await userEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    await userEvent.clear(screen.getByRole('textbox', { name: 'Project name' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Project name' }), 'New name')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Rename project' })).toHaveFocus())
  })
})
