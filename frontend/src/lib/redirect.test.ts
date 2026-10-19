import { safeNext } from '@/lib/redirect'

describe('safeNext (post-login redirect)', () => {
  it.each([
    ['/projects/123', '/projects/123'],
    ['/settings?tab=keys', '/settings?tab=keys'],
  ])('keeps in-app path %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })

  it.each([null, '', 'https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)'])(
    'rejects %s',
    (input) => {
      expect(safeNext(input)).toBe('/projects')
    },
  )
})
