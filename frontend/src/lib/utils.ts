import { createCn } from 'cn/config'

// Our type-scale utilities (src/index.css @utility text-*) are font sizes, not colours; without this
// cn('text-caption', 'text-muted-foreground') would drop the size.
export const cn = createCn({
  extend: {
    classGroups: {
      'font-size': [{ text: ['display', 'display-sm', 'page-title', 'section-title', 'card-title', 'body', 'caption', 'eyebrow', 'overline', 'metric'] }],
    },
  },
})
