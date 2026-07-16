import { describe, it, expect } from 'vitest'
import { widgetReducer } from './widgetReducer'
import type { Widget } from './types'

const w = (key: string, updatedAt = 1): Widget =>
  ({ key, type: 'map', title: key, props: {}, updatedAt })

describe('widgetReducer', () => {
  it('appends a new widget', () => {
    const next = widgetReducer([], { type: 'upsert', widget: w('map:75248') })
    expect(next).toHaveLength(1)
  })

  it('upserts by key in place - no duplicates, position preserved', () => {
    const state = [w('map:75248'), w('table:75248')]
    const next = widgetReducer(state, { type: 'upsert', widget: w('map:75248', 2) })
    expect(next).toHaveLength(2)
    expect(next[0].updatedAt).toBe(2)
    expect(next[0].key).toBe('map:75248')
  })

  it('dismisses by key', () => {
    const state = [w('map:75248'), w('table:75248')]
    const next = widgetReducer(state, { type: 'dismiss', key: 'map:75248' })
    expect(next.map(x => x.key)).toEqual(['table:75248'])
  })

  it('dismiss of unknown key is a no-op', () => {
    const state = [w('map:75248')]
    expect(widgetReducer(state, { type: 'dismiss', key: 'nope' })).toHaveLength(1)
  })

  it('clear empties the canvas', () => {
    expect(widgetReducer([w('a'), w('b')], { type: 'clear' })).toEqual([])
  })
})
