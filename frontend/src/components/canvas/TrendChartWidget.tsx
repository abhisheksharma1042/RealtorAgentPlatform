// frontend/src/components/canvas/TrendChartWidget.tsx
import TimeSeriesChart from '../charts/TimeSeriesChart'

export default function TrendChartWidget({ result }: { result: any }) {
  const history: any[] = result?.history ?? []
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No trend history available.</p>
  }
  return (
    <div className="p-2">
      <TimeSeriesChart data={history} metric="median_price" zipCode={result?.zip_code} />
      <div className="px-2 pb-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>Median: ${result?.median_price?.toLocaleString() ?? '—'}</span>
        <span>Avg DOM: {result?.avg_days_on_market ?? '—'}</span>
      </div>
    </div>
  )
}
