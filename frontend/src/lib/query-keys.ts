// Single source of TanStack Query keys, so invalidation always matches.
export type ChunkParams = { documentId?: string; q?: string }
export type PairFilters = {
  split: 'train' | 'eval' | 'all'
  kept: 'all' | 'kept' | 'dropped'
  q: string
  sort: 'created' | 'score' | '-score'
}

export const qk = {
  me: () => ['me'] as const,
  meta: () => ['meta'] as const,
  projects: () => ['projects'] as const,
  project: (id: string) => ['project', id] as const,
  documents: (id: string) => ['documents', id] as const,
  /** Prefix for every chunk query of a project (for invalidation). */
  chunksAll: (id: string) => ['chunks', id] as const,
  chunks: (id: string, params: ChunkParams = {}) => ['chunks', id, params] as const,
  providers: () => ['providers'] as const,
  keys: () => ['keys'] as const,
  /** Timestamp (ms) until which the key list is polled while a key is unverified. */
  keysPollUntil: () => ['keys', 'poll-until'] as const,
  kaggle: () => ['compute', 'kaggle'] as const,
  /** Timestamp (ms) until which the Kaggle account is polled while its status is `unchecked`. */
  kagglePollUntil: () => ['compute', 'kaggle', 'poll-until'] as const,
  styleTemplates: () => ['style-templates'] as const,
  datasetFormats: () => ['dataset-formats'] as const,
  runPairs: (id: string, runId: string) => ['run-pairs', id, runId] as const,
  estimate: (id: string) => ['estimate', id] as const,
  /** Prefix for every dataset query (pairs, stats) of a project. */
  datasetAll: (id: string) => ['dataset', id] as const,
  pairs: (id: string, filters: PairFilters) => ['dataset', id, 'pairs', filters] as const,
  datasetStats: (id: string) => ['dataset', id, 'stats'] as const,
  /** Latest `notice` SSE event for a project (written by the stream, read by GenerationPanel). */
  notice: (id: string) => ['notice', id] as const,
  activity: (id: string) => ['activity', id] as const,
  modelCatalog: (projectId: string) => ['models', 'catalog', projectId] as const,
  presets: () => ['training', 'presets'] as const,
  /** Loss curve of one training job (filled by the metrics endpoint and the `train_metrics` stream). */
  metrics: (id: string, jobId: string) => ['training', id, jobId, 'metrics'] as const,
  artifacts: (id: string) => ['artifacts', id] as const,
  evaluation: (id: string) => ['evaluation', id] as const,
  playgroundStatus: (id: string) => ['playground', id, 'status'] as const,
}
