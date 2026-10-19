import { render, screen } from '@testing-library/react'

import { StatusBadge } from '@/components/StatusBadge'
import { statusMeta } from '@/components/status-meta'
import type { ProjectStatus } from '@/features/projects/api'

const statuses = Object.keys(statusMeta) as ProjectStatus[]

describe('StatusBadge', () => {
  it('covers all 13 statuses', () => {
    expect(statuses).toHaveLength(13)
  })

  it.each(statuses)('renders a text label for %s', (status) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(statusMeta[status].label)).toBeInTheDocument()
  })

  it('uses distinct labels', () => {
    const labels = statuses.map((s) => statusMeta[s].label)
    expect(new Set(labels).size).toBe(labels.length)
  })
})
