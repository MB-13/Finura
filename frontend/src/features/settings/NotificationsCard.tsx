import { useId } from 'react'
import { toast } from 'sonner'

import { useUpdateMe, type Me } from '@/features/me/api'

/** The card body only: the page's "Notifications" section provides the heading. */
export function NotificationsCard({ me }: { me: Me }) {
  const update = useUpdateMe()
  const id = useId()
  return (
    <div role="region" aria-label="Notifications">
        <label htmlFor={id} className="flex cursor-pointer items-start gap-3 text-sm">
          <input
            id={id}
            type="checkbox"
            className="mt-0.5 size-4 shrink-0 accent-primary"
            checked={me.email_notifications}
            disabled={update.isPending}
            onChange={(e) =>
              update.mutate({ email_notifications: e.target.checked }, { onError: (err) => toast.error(err.message) })
            }
          />
          <span className="flex flex-col gap-0.5">
            <span className="font-medium">Email me when training pauses or finishes</span>
            <span className="text-caption text-muted-foreground">
              For example when Colab disconnects and you need to run the notebook again.
            </span>
          </span>
        </label>
    </div>
  )
}
