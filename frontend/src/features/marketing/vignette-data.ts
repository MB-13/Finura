export const REVIEW_PAIRS = [
  {
    q: 'How do I reset my password?',
    a: 'Open Settings, choose Reset password, and follow the link we email you.',
    state: 'approved' as const,
    scores: [4.5, 5] as [number, number],
  },
  {
    q: 'Can I change my delivery address?',
    a: 'Yes, until the order ships. Go to Orders and choose Edit address.',
    state: 'edited' as const,
    scores: [4, 4.5] as [number, number],
  },
  {
    q: 'Do you ship abroad?',
    a: 'We ship to 30 countries. Delivery times show at checkout.',
    state: 'review' as const,
    scores: [3.5, 4] as [number, number],
  },
]
