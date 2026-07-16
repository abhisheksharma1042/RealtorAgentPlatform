// frontend/src/components/canvas/WidgetFrame.tsx
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

interface WidgetFrameProps {
  title: string
  onClose: () => void
  children: ReactNode
}

export default function WidgetFrame({ title, onClose, children }: WidgetFrameProps) {
  return (
    <div className="bg-card border border-border rounded-xl shadow-sm flex flex-col overflow-hidden min-h-[280px]">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/10 flex-shrink-0">
        <span className="text-sm font-semibold text-card-foreground truncate">{title}</span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors"
          aria-label={`Close ${title}`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </div>
  )
}
