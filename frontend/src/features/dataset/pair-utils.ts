import type { Pair } from '@/features/dataset/api'

export const ROW_GRID =
  'md:grid md:grid-cols-[1.5rem_minmax(0,1fr)_minmax(0,1.3fr)_4rem_7.5rem_6.5rem_minmax(0,6.5rem)_6.25rem] md:items-start md:gap-4'

/** `kept === null` means not judged yet, which is not the same as dropped. */
export const isDropped = (pair: Pair) => pair.kept === false
