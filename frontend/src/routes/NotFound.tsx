import { Compass } from 'lucide-react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'

export function NotFound() {
  return (
    <div className="relative mx-auto max-w-lg px-4 py-20 sm:py-28">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-glow" />
      <h1 className="sr-only">Error 404</h1>
      <div aria-hidden className="relative mb-2 text-center text-metric text-6xl text-muted-foreground/40">
        404
      </div>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="This page doesn't exist or has moved. Check the address, or head back to somewhere familiar."
        action={
          <>
            <Button asChild>
              <Link to="/projects">Go to your projects</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/">Go home</Link>
            </Button>
          </>
        }
      />
    </div>
  )
}
