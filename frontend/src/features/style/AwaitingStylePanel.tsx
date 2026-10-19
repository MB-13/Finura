import { useState } from 'react'

import type { Project } from '@/features/projects/api'
import { DocumentsSection } from '@/features/style/DocumentsSection'
import { PreviewResults } from '@/features/style/PreviewResults'
import { StylePanel } from '@/features/style/StylePanel'

/** `awaiting_style`: preview results (if any), the style form and the collapsible documents. */
export function AwaitingStylePanel({ project }: { project: Project }) {
  const [focusSignal, setFocusSignal] = useState(0)
  return (
    <div className="flex flex-col gap-8">
      {project.latest_preview && <PreviewResults project={project} onTweak={() => setFocusSignal((n) => n + 1)} />}
      <StylePanel project={project} focusSignal={focusSignal} />
      <DocumentsSection project={project} />
    </div>
  )
}
