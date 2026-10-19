import { cn } from '@/lib/utils'

describe('cn', () => {
  it('keeps type-scale utilities next to text colours', () => {
    expect(cn('text-card-title', 'text-info-muted-foreground')).toBe('text-card-title text-info-muted-foreground')
    expect(cn('text-caption text-muted-foreground', 'text-foreground')).toBe('text-caption text-foreground')
  })

  it('still lets a later size win over an earlier one', () => {
    expect(cn('text-body', 'text-caption')).toBe('text-caption')
    expect(cn('text-sm', 'text-card-title')).toBe('text-card-title')
  })
})
