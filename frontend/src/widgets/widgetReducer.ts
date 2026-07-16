import type { Widget, WidgetAction } from './types'

// Pure - React StrictMode double-invokes reducers in dev; upsert-by-key
// makes that harmless (same action twice yields the same state).
export function widgetReducer(state: Widget[], action: WidgetAction): Widget[] {
  switch (action.type) {
    case 'upsert': {
      const idx = state.findIndex(w => w.key === action.widget.key)
      if (idx >= 0) return state.map((w, i) => (i === idx ? action.widget : w))
      return [...state, action.widget]
    }
    case 'dismiss':
      return state.filter(w => w.key !== action.key)
    case 'clear':
      return []
    default:
      return state
  }
}
