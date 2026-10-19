import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/auth-context'
import { useDeleteAccount } from '@/features/me/api'

export function DeleteAccountCard() {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState('')
  const remove = useDeleteAccount()
  const { signOut } = useAuth()
  const navigate = useNavigate()

  async function onDelete() {
    remove.mutate(undefined, {
      onSuccess: async () => {
        toast.success('Your account is being deleted.')
        await signOut()
        void navigate('/', { replace: true })
      },
    })
  }

  return (
    <Card className="border-destructive/30">
      <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="text-card-title">Delete this account</div>
          <p className="text-sm text-muted-foreground">
            Deleting your account removes all your projects, files, keys and models. This cannot be undone.
          </p>
        </div>
        <Button variant="destructive" className="shrink-0 self-start sm:self-auto" onClick={() => setOpen(true)}>
          <Trash2 aria-hidden /> Delete account
        </Button>
      </CardContent>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setConfirm('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              Everything is deleted: projects, uploaded files, generated data, API keys and training files. Files in your own Google Drive are not touched.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="delete-confirm">
              Type <strong>DELETE</strong> to confirm
            </Label>
            <Input id="delete-confirm" value={confirm} autoComplete="off" onChange={(e) => setConfirm(e.target.value)} />
          </div>
          {remove.isError && (
            <p role="alert" className="text-sm text-destructive-muted-foreground">
              {remove.error.message}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Keep my account
            </Button>
            <Button variant="destructive" disabled={confirm !== 'DELETE' || remove.isPending} onClick={() => void onDelete()}>
              {remove.isPending ? 'Deleting…' : 'Delete everything'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
