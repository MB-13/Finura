import { UploadCloud } from 'lucide-react'
import { useId, useState, type DragEvent } from 'react'

import { ACCEPT_ATTR } from '@/features/documents/upload'
import { cn } from '@/lib/utils'

type Props = { onFiles: (files: File[]) => void; disabled?: boolean; hint: string }

/** Accessible dropzone: a label around a visually hidden file input, plus drag events. */
export function FileDropzone({ onFiles, disabled = false, hint }: Props) {
  const [dragging, setDragging] = useState(false)
  const hintId = useId()

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) onFiles(files)
  }

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        'group flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed bg-card/50 px-6 py-10 text-center transition-colors',
        'hover:border-primary/50 hover:bg-accent/40 focus-within:border-primary focus-within:ring-[3px] focus-within:ring-ring/50',
        dragging && 'border-primary bg-accent',
        disabled && 'cursor-not-allowed opacity-50 hover:border-border hover:bg-card/50',
      )}
    >
      <span
        className={cn(
          'flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground transition-transform',
          dragging && 'scale-110 bg-primary text-primary-foreground',
        )}
      >
        <UploadCloud className="size-6" aria-hidden />
      </span>
      <span className="flex flex-col gap-1">
        <span className="text-card-title">{dragging ? 'Release to add your files' : 'Drop files here or click to choose'}</span>
        <span id={hintId} className="text-caption text-muted-foreground">
          {hint}
        </span>
      </span>
      <input
        type="file"
        multiple
        accept={ACCEPT_ATTR}
        disabled={disabled}
        aria-describedby={hintId}
        className="sr-only"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          if (files.length > 0) onFiles(files)
          e.target.value = '' // allow choosing the same file again
        }}
      />
    </label>
  )
}
