import { useId, useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useCreatePair } from '@/features/dataset/api'
import { emptyRecord, recordProblem, trimRecord, type DatasetFormat, type PairRecord } from '@/features/dataset/record-utils'
import { RecordEditor } from '@/features/dataset/RecordEditor'
import { ApiError } from '@/lib/api/client'

type Props = { projectId: string; format: DatasetFormat; open: boolean; onOpenChange: (open: boolean) => void }

const DESCRIPTIONS: Record<DatasetFormat, string> = {
  qa_chat: 'Write your own question and the answer you want the model to give.',
  instruction: 'Write a task, the text it works on if any, and the output you want the model to give.',
  multi_turn: 'Write a short conversation. Every assistant turn is something the model learns to say.',
}

export function AddPairDialog({ projectId, format, open, onOpenChange }: Props) {
  const create = useCreatePair(projectId)
  const id = useId()
  const [record, setRecord] = useState<PairRecord>(() => emptyRecord(format))
  const [split, setSplit] = useState<'train' | 'eval'>('train')
  const [localError, setLocalError] = useState<string | null>(null)
  const fields = create.error instanceof ApiError ? create.error.fieldErrors : {}
  const generic = create.error && Object.keys(fields).length === 0 ? create.error.message : null
  // the dialog can stay mounted while the project's format changes (restyle)
  const current = record.format === format ? record : emptyRecord(format)

  function submit(e: FormEvent) {
    e.preventDefault()
    const problem = recordProblem(current)
    if (problem) {
      setLocalError(problem)
      return
    }
    setLocalError(null)
    create.mutate(
      { record: trimRecord(current), split },
      {
        onSuccess: () => {
          toast.success('Pair added')
          setRecord(emptyRecord(format))
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add a pair</DialogTitle>
          <DialogDescription>{DESCRIPTIONS[format]}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <RecordEditor record={current} onChange={setRecord} errors={fields} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-s`}>Use for</Label>
            <NativeSelect id={`${id}-s`} value={split} onChange={(e) => setSplit(e.target.value as 'train' | 'eval')}>
              <option value="train">Training</option>
              <option value="eval">Evaluation</option>
            </NativeSelect>
          </div>
          {(localError ?? generic) && (
            <p role="alert" className="text-sm text-destructive">
              {localError ?? generic}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Adding…' : 'Add pair'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
