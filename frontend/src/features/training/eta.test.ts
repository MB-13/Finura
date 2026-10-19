import { estimateEtaSeconds, trainingPercent } from '@/features/training/eta'

const pt = (step: number, sec: number) => ({ step, loss: 1, lr: null, at: new Date(Date.UTC(2026, 0, 1, 0, 0, sec)).toISOString() })

describe('estimateEtaSeconds', () => {
  it('needs two points', () => {
    expect(estimateEtaSeconds([], 0, 100)).toBeNull()
    expect(estimateEtaSeconds([pt(10, 0)], 10, 100)).toBeNull()
  })

  it('uses the recent step rate', () => {
    // 10 steps every 20 s -> 0.5 steps/s; 80 steps left -> 160 s
    expect(estimateEtaSeconds([pt(10, 0), pt(20, 20)], 20, 100)).toBe(160)
  })

  it('is null when done or time did not advance', () => {
    expect(estimateEtaSeconds([pt(10, 0), pt(20, 20)], 100, 100)).toBeNull()
    expect(estimateEtaSeconds([pt(10, 5), pt(20, 5)], 20, 100)).toBeNull()
  })
})

describe('trainingPercent', () => {
  it('floors and caps', () => {
    expect(trainingPercent(1, 3)).toBe(33)
    expect(trainingPercent(5, 3)).toBe(100)
    expect(trainingPercent(0, 0)).toBe(0)
  })
})
