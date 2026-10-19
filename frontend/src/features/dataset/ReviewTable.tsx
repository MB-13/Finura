import { useWindowVirtualizer } from '@tanstack/react-virtual'
import { Inbox, Plus, Search, SearchX } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { AddPairDialog } from '@/features/dataset/AddPairDialog'
import {
  DEFAULT_FILTERS,
  useBulkPairs,
  usePairs,
  useUpdatePair,
  type BulkAction,
  type Pair,
} from '@/features/dataset/api'
import { isDropped, ROW_GRID } from '@/features/dataset/pair-utils'
import { PairRow } from '@/features/dataset/PairRow'
import { LABELS } from '@/features/dataset/record-utils'
import type { Project } from '@/features/projects/api'
import { type PairFilters } from '@/lib/query-keys'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import { cn } from '@/lib/utils'

const ESTIMATED_ROW_HEIGHT = 84

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/** Overlays that own the keyboard while open: dialogs, and Radix menus / listboxes (which do not stop key events). */
const OVERLAY_SELECTOR = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [data-radix-menu-content]'

function inOverlay(target: EventTarget | null): boolean {
  return (target instanceof Element && target.closest(OVERLAY_SELECTOR) !== null) || document.querySelector(OVERLAY_SELECTOR) !== null
}

const BULK_ACTIONS: { action: BulkAction; label: string }[] = [
  { action: 'drop', label: 'Drop' },
  { action: 'restore', label: 'Restore' },
  { action: 'move_to_train', label: 'Move to train' },
  { action: 'move_to_eval', label: 'Move to eval' },
]

export function ReviewTable({ project }: { project: Project }) {
  const readOnly = project.status !== 'in_review'
  const format = project.style?.dataset_format ?? 'qa_chat'
  const labels = LABELS[format]
  const [search, setSearch] = useState('')
  const q = useDebouncedValue(search.trim(), 300)
  const [split, setSplit] = useState<PairFilters['split']>(DEFAULT_FILTERS.split)
  const [kept, setKept] = useState<PairFilters['kept']>(DEFAULT_FILTERS.kept)
  const [sort, setSort] = useState<PairFilters['sort']>(DEFAULT_FILTERS.sort)
  const filters = useMemo<PairFilters>(() => ({ split, kept, q, sort }), [split, kept, q, sort])

  const pairs = usePairs(project.id, filters)
  const update = useUpdatePair(project.id)
  const bulk = useBulkPairs(project.id)
  const items = useMemo<Pair[]>(() => pairs.data?.pages.flatMap((p) => p.items) ?? [], [pairs.data])

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [focusedIndex, setFocusedIndex] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const pendingFocus = useRef(false)
  const listRef = useRef<HTMLDivElement>(null)

  // TanStack Virtual returns un-memoizable functions; it is only used inside this component
  // oxlint-disable-next-line react/incompatible-library
  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 8,
    scrollMargin: listRef.current?.offsetTop ?? 0,
    getItemKey: (i) => items[i]?.id ?? i,
  })

  // keep focus + selection valid when the list changes
  const safeFocus = Math.min(focusedIndex, Math.max(items.length - 1, 0))
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev
      const ids = new Set(items.map((p) => p.id))
      const next = new Set([...prev].filter((id) => ids.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [items])

  // move DOM focus to the keyboard-focused row once it is mounted
  useLayoutEffect(() => {
    if (!pendingFocus.current) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-row-index="${safeFocus}"]`)
    if (el) {
      el.focus()
      pendingFocus.current = false
    }
  })

  const toggleKept = useCallback(
    (pair: Pair) => {
      const nextKept = isDropped(pair)
      update.mutate(
        { id: pair.id, kept: nextKept },
        { onError: (err) => toast.error(`Couldn't ${nextKept ? 'restore' : 'drop'} the pair: ${err.message}`) },
      )
    },
    [update],
  )
  const toggleSplit = useCallback(
    (pair: Pair) => {
      update.mutate(
        { id: pair.id, split: pair.split === 'train' ? 'eval' : 'train' },
        { onError: (err) => toast.error(`Couldn't move the pair: ${err.message}`) },
      )
    },
    [update],
  )

  // keyboard: j/k move, e edit, d drop, r restore (never while typing or while a dialog / menu is open)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target) || addOpen) return
      if (inOverlay(e.target)) return
      const pair = items[safeFocus]
      switch (e.key) {
        case 'j':
        case 'k': {
          if (items.length === 0) return
          const next = Math.max(0, Math.min(items.length - 1, safeFocus + (e.key === 'j' ? 1 : -1)))
          pendingFocus.current = true
          setFocusedIndex(next)
          virtualizer.scrollToIndex(next)
          break
        }
        case 'e':
          if (!pair) return
          setExpandedId((id) => (id === pair.id ? null : pair.id))
          break
        case 'd':
          if (readOnly || !pair || isDropped(pair)) return
          toggleKept(pair)
          break
        case 'r':
          if (readOnly || !pair || !isDropped(pair)) return
          toggleKept(pair)
          break
        default:
          return
      }
      e.preventDefault()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [items, safeFocus, readOnly, addOpen, toggleKept, virtualizer])

  function runBulk(action: BulkAction) {
    bulk.mutate(
      { ids: [...selected], action },
      {
        onSuccess: ({ updated }) => {
          toast.success(`${updated} ${updated === 1 ? 'pair' : 'pairs'} updated`)
          setSelected(new Set())
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const allSelected = items.length > 0 && items.every((p) => selected.has(p.id))
  const virtualItems = virtualizer.getVirtualItems()
  const barVisible = !readOnly && selected.size > 0
  const filtered = split !== 'all' || kept !== 'all' || q !== ''

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        back={{ to: `/projects/${project.id}`, label: `Back to ${project.name}` }}
        title="Review dataset"
        badge={project.dataset_version && <Badge variant="success">Approved v{project.dataset_version.version}</Badge>}
        description="Check each pair. Fix wording, drop weak pairs, or move them between training and evaluation."
        actions={
          !readOnly && (
            <Button onClick={() => setAddOpen(true)}>
              <Plus aria-hidden /> Add pair
            </Button>
          )
        }
      />

      {readOnly && (
        <Callout tone="info" role="status">
          This dataset is read-only because the project is no longer in review.
        </Callout>
      )}

      <div
        className="grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 lg:grid-cols-[minmax(0,1fr)_7rem_11rem_12rem]"
        role="search"
        aria-label="Filter pairs"
      >
        <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-3 lg:col-span-1">
          <Label htmlFor="pairs-search" className="text-eyebrow text-[0.6875rem]">
            Search
          </Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" aria-hidden />
            <Input id="pairs-search" type="search" className="pl-9" placeholder="Search questions and answers" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pairs-split" className="text-eyebrow text-[0.6875rem]">
            Split
          </Label>
          <NativeSelect id="pairs-split" value={split} onChange={(e) => setSplit(e.target.value as PairFilters['split'])}>
            <option value="all">All</option>
            <option value="train">Train</option>
            <option value="eval">Eval</option>
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pairs-kept" className="text-eyebrow text-[0.6875rem]">
            Status
          </Label>
          <NativeSelect id="pairs-kept" value={kept} onChange={(e) => setKept(e.target.value as PairFilters['kept'])}>
            <option value="all">Kept and dropped</option>
            <option value="kept">Kept</option>
            <option value="dropped">Dropped</option>
          </NativeSelect>
        </div>
        <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-1">
          <Label htmlFor="pairs-sort" className="text-eyebrow text-[0.6875rem]">
            Sort
          </Label>
          <NativeSelect id="pairs-sort" value={sort} onChange={(e) => setSort(e.target.value as PairFilters['sort'])}>
            <option value="created">Newest first</option>
            <option value="-score">Highest score first</option>
            <option value="score">Lowest score first</option>
          </NativeSelect>
        </div>
      </div>

      {pairs.isPending ? (
        <div aria-busy="true" aria-label="Loading pairs" className="flex flex-col gap-2">
          <Skeleton className="h-9 rounded-xl" />
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-20 rounded-xl" />
        </div>
      ) : pairs.isError ? (
        <ErrorState message={pairs.error.message} onRetry={() => pairs.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={filtered ? SearchX : Inbox}
          title={filtered ? 'No pairs match these filters' : 'No pairs yet'}
          description={filtered ? 'Try clearing the search or filters.' : 'Generated pairs will show up here.'}
          action={
            filtered ? (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch('')
                  setSplit(DEFAULT_FILTERS.split)
                  setKept(DEFAULT_FILTERS.kept)
                }}
              >
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="-mb-2 flex flex-wrap items-center justify-between gap-x-6 gap-y-1 text-caption text-muted-foreground">
            <p aria-live="polite" className="tabular-nums">
              Showing {items.length} {items.length === 1 ? 'pair' : 'pairs'}
              {pairs.hasNextPage ? ' so far' : ''}
            </p>
            <p className="hidden items-center gap-3 md:flex" aria-label="Keyboard shortcuts">
              {(
                [
                  ['j / k', 'move'],
                  ['e', 'edit'],
                  ['d', 'drop'],
                  ['r', 'restore'],
                ] as const
              ).map(([key, what]) => (
                <span key={key} className="inline-flex items-center gap-1.5">
                  <kbd className="rounded border bg-card px-1.5 py-px font-mono text-[0.6875rem] font-medium text-foreground/80 shadow-xs">{key}</kbd>
                  {what}
                </span>
              ))}
            </p>
          </div>
          {barVisible && (
            <div
              role="toolbar"
              aria-label="Bulk actions"
              // sticks just under the app header (h-14); the table header below tucks under its bottom edge (top-[6.75rem])
              className="sticky top-[3.75rem] z-20 flex flex-wrap items-center gap-1.5 rounded-lg border border-primary/30 bg-card p-1.5 pl-3.5 shadow-md ring-1 ring-primary/10"
            >
              <span className="text-metric mr-auto text-sm">{selected.size} selected</span>
              {BULK_ACTIONS.map(({ action, label }) => (
                <Button key={action} variant="outline" size="sm" disabled={bulk.isPending} onClick={() => runBulk(action)}>
                  {label}
                </Button>
              ))}
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
            </div>
          )}
          <div role="table" aria-label="Dataset pairs" aria-rowcount={items.length + 1} className="flex flex-col md:rounded-xl md:border md:bg-card md:shadow-card">
            <div
              role="row"
              aria-rowindex={1}
              className={cn('sticky z-10 hidden rounded-t-xl border-b bg-muted px-4 py-2 text-eyebrow', barVisible ? 'top-[6.75rem]' : 'top-14', ROW_GRID)}
            >
              <div role="columnheader">
                {!readOnly && (
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    aria-label="Select all loaded pairs"
                    checked={allSelected}
                    onChange={(e) => setSelected(e.target.checked ? new Set(items.map((p) => p.id)) : new Set())}
                  />
                )}
              </div>
              <div role="columnheader">{labels.input}</div>
              <div role="columnheader">{labels.output}</div>
              <div role="columnheader">Split</div>
              <div role="columnheader">Scores</div>
              <div role="columnheader">Origin</div>
              <div role="columnheader">Source</div>
              <div role="columnheader">
                <span className="sr-only">Actions</span>
              </div>
            </div>
            <div ref={listRef} role="rowgroup" style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
              {virtualItems.map((v) => {
                const pair = items[v.index]
                if (!pair) return null
                return (
                  <div
                    key={v.key}
                    ref={virtualizer.measureElement}
                    data-index={v.index}
                    className="absolute top-0 left-0 w-full pb-3 md:pb-0"
                    style={{ transform: `translateY(${v.start - virtualizer.options.scrollMargin}px)` }}
                  >
                    <PairRow
                      pair={pair}
                      rowIndex={v.index}
                      readOnly={readOnly}
                      selected={selected.has(pair.id)}
                      focused={v.index === safeFocus}
                      expanded={expandedId === pair.id}
                      saving={update.isPending && update.variables?.id === pair.id}
                      onSelect={(on) =>
                        setSelected((prev) => {
                          const next = new Set(prev)
                          if (on) next.add(pair.id)
                          else next.delete(pair.id)
                          return next
                        })
                      }
                      onToggleExpand={() => setExpandedId((id) => (id === pair.id ? null : pair.id))}
                      onToggleKept={() => toggleKept(pair)}
                      onToggleSplit={() => toggleSplit(pair)}
                      onSave={async (record) => {
                        await update.mutateAsync({ id: pair.id, record })
                        setExpandedId(null)
                        toast.success('Pair saved')
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </div>
          {pairs.hasNextPage && (
            <Button variant="outline" className="self-center" disabled={pairs.isFetchingNextPage} onClick={() => pairs.fetchNextPage()}>
              {pairs.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </Button>
          )}
        </>
      )}

      {!readOnly && <AddPairDialog projectId={project.id} format={format} open={addOpen} onOpenChange={setAddOpen} />}
    </div>
  )
}
