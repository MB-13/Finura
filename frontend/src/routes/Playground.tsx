import { useParams } from 'react-router'

import { PlaygroundPage } from '@/features/playground/PlaygroundPage'

export function Playground() {
  const { id = '' } = useParams()
  return <PlaygroundPage projectId={id} />
}
