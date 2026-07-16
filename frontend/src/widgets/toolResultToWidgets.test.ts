import { describe, it, expect } from 'vitest'
import { toolResultToActions } from './toolResultToWidgets'

describe('toolResultToActions', () => {
  it('comparable_sales spawns map + table keyed by zip', () => {
    const actions = toolResultToActions(
      { type: 'comparable_sales', zip_code: '75248', properties: [], map_markers: [] }, 10)
    expect(actions.map(a => a.type === 'upsert' && a.widget.key))
      .toEqual(['map:75248', 'table:75248'])
  })

  it('market_data spawns a trend widget', () => {
    const actions = toolResultToActions(
      { type: 'market_data', zip_code: '75205', history: [] }, 10)
    expect(actions).toHaveLength(1)
    expect(actions[0].type === 'upsert' && actions[0].widget.type).toBe('trend_chart')
  })

  it('market_data with error spawns nothing', () => {
    expect(toolResultToActions({ type: 'market_data', zip_code: 'x', error: 'nope' }, 1))
      .toEqual([])
  })

  it('pin_update spawns a property card; errors do not', () => {
    const ok = toolResultToActions(
      { type: 'pin_update', action: 'pinned', property: { id: 'abc', address: 'X' } }, 1)
    expect(ok[0].type === 'upsert' && ok[0].widget.key).toBe('card:abc')
    expect(toolResultToActions({ type: 'pin_update', error: 'ambiguous' }, 1)).toEqual([])
  })

  it('data_coverage spawns the coverage widget', () => {
    const actions = toolResultToActions(
      { type: 'data_coverage', coverage: [], boundaries: [] }, 1)
    expect(actions[0].type === 'upsert' && actions[0].widget.key).toBe('coverage')
  })

  it('widget_dismiss maps to a dismiss action', () => {
    expect(toolResultToActions({ type: 'widget_dismiss', widget_key: 'map:75248' }, 1))
      .toEqual([{ type: 'dismiss', key: 'map:75248' }])
  })

  it('unknown or malformed results are ignored', () => {
    expect(toolResultToActions({ type: 'something_new' }, 1)).toEqual([])
    expect(toolResultToActions(null, 1)).toEqual([])
    expect(toolResultToActions('junk', 1)).toEqual([])
  })
})
