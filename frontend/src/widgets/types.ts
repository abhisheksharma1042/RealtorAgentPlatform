export type WidgetType =
  | 'map'
  | 'comps_table'
  | 'trend_chart'
  | 'property_card'
  | 'coverage_map'

export interface Widget {
  key: string        // content identity: map:75248, table:75248, trend:75248, card:<id>, coverage
  type: WidgetType
  title: string
  props: any         // the raw tool result the widget body renders
  updatedAt: number
}

export type WidgetAction =
  | { type: 'upsert'; widget: Widget }
  | { type: 'dismiss'; key: string }
  | { type: 'clear' }
