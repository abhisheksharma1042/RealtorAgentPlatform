import type { Widget, WidgetAction } from './types'

const widget = (
  key: string, type: Widget['type'], title: string, props: any, updatedAt: number,
): WidgetAction => ({ type: 'upsert', widget: { key, type, title, props, updatedAt } })

// Pure mapping: SSE tool result -> reducer actions. Unknown types are
// ignored so new backend widgets can't break an old frontend.
export function toolResultToActions(result: any, now: number): WidgetAction[] {
  if (!result || typeof result !== 'object') return []
  switch (result.type) {
    case 'comparable_sales': {
      const zip = result.zip_code ?? 'latest'
      const label = result.saved_search_name ? ` — ${result.saved_search_name}` : ''
      return [
        widget(`map:${zip}`, 'map', `Map — ${zip}${label}`, result, now),
        widget(`table:${zip}`, 'comps_table', `Comps — ${zip}${label} (${result.count ?? 0})`, result, now),
      ]
    }
    case 'market_data': {
      if (result.error) return []
      const zip = result.zip_code ?? 'latest'
      return [widget(`trend:${zip}`, 'trend_chart', `Trend — ${zip}`, result, now)]
    }
    case 'pin_update': {
      if (result.error || !result.property || result.action !== 'pinned') return []
      return [widget(
        `card:${result.property.id}`, 'property_card',
        result.property.address ?? 'Pinned property', result, now,
      )]
    }
    case 'data_coverage': {
      if (result.error) return []
      return [widget('coverage', 'coverage_map', 'Data coverage', result, now)]
    }
    case 'widget_dismiss':
      return [{ type: 'dismiss', key: result.widget_key }]
    default:
      return []
  }
}
