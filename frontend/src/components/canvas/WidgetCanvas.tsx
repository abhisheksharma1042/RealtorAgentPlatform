// frontend/src/components/canvas/WidgetCanvas.tsx
import type { Dispatch } from 'react'
import type { Widget, WidgetAction } from '../../widgets/types'
import WidgetFrame from './WidgetFrame'
import MapWidget from './MapWidget'
import CompsTableWidget from './CompsTableWidget'
import TrendChartWidget from './TrendChartWidget'
import PropertyCardWidget from './PropertyCardWidget'
import CoverageMapWidget from './CoverageMapWidget'
import { LayoutGrid } from 'lucide-react'

interface WidgetCanvasProps {
  widgets: Widget[]
  dispatch: Dispatch<WidgetAction>
  onMemoryChange: () => void
  memoryVersion?: number
}

function WidgetBody(
  { w, onMemoryChange, memoryVersion }:
  { w: Widget; onMemoryChange: () => void; memoryVersion?: number },
) {
  switch (w.type) {
    case 'map': return <MapWidget result={w.props} />
    case 'comps_table':
      return (
        <CompsTableWidget result={w.props} onMemoryChange={onMemoryChange}
                           memoryVersion={memoryVersion} />
      )
    case 'trend_chart': return <TrendChartWidget result={w.props} />
    case 'property_card': return <PropertyCardWidget result={w.props} />
    case 'coverage_map': return <CoverageMapWidget result={w.props} />
    default:
      return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(w.props, null, 2)}</pre>
  }
}

export default function WidgetCanvas({ widgets, dispatch, onMemoryChange, memoryVersion }: WidgetCanvasProps) {
  if (widgets.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center space-y-3">
          <LayoutGrid className="h-12 w-12 text-muted-foreground mx-auto" />
          <p className="text-sm text-muted-foreground max-w-xs">
            Ask Plutus a question - analysis widgets will appear here.
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="h-full overflow-y-auto p-3 bg-background">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {widgets.map(w => (
          <WidgetFrame key={w.key} title={w.title}
                       onClose={() => dispatch({ type: 'dismiss', key: w.key })}>
            <WidgetBody w={w} onMemoryChange={onMemoryChange} memoryVersion={memoryVersion} />
          </WidgetFrame>
        ))}
      </div>
    </div>
  )
}
