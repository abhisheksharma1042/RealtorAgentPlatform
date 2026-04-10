import { FileText, TrendingUp, Home, BarChart3, Clock } from 'lucide-react'
import ScatterChart from '../charts/ScatterChart'
import TimeSeriesChart from '../charts/TimeSeriesChart'
import ReactMarkdown from 'react-markdown'
import type { QuerySession } from '../../App'

interface OutputPanelProps {
  history: QuerySession[]
}

export default function OutputPanel({ history }: OutputPanelProps) {
  const renderToolResult = (result: any, index: number) => {
    if (result.type === 'market_data') {
      return (
        <div key={index} className="space-y-4">
          <div className="border border-border rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              <h3 className="font-semibold text-card-foreground">
                Market Data - {result.area_name || result.zip_code}
              </h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Median Price</p>
                <p className="text-lg font-semibold text-foreground">
                  ${result.median_price?.toLocaleString()}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Avg Price</p>
                <p className="text-lg font-semibold text-foreground">
                  ${result.avg_price?.toLocaleString()}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Sales Volume</p>
                <p className="text-lg font-semibold text-foreground">
                  {result.sales_volume}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Avg DOM</p>
                <p className="text-lg font-semibold text-foreground">
                  {result.avg_days_on_market} days
                </p>
              </div>
            </div>

            {result.price_change_1y && (
              <div className="pt-3 border-t border-border">
                <p className="text-sm">
                  <span className="text-muted-foreground">YoY Change: </span>
                  <span
                    className={`font-semibold ${
                      result.price_change_1y > 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {result.price_change_1y > 0 ? '+' : ''}
                    {result.price_change_1y}%
                  </span>
                </p>
              </div>
            )}
          </div>
        </div>
      )
    }

    if (result.type === 'comparable_sales') {
      return (
        <div key={index} className="space-y-4">
          <div className="flex items-center gap-2">
            <Home className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-card-foreground">
              Comparable Sales - {result.zip_code}
            </h3>
            <span className="text-sm text-muted-foreground">
              ({result.count} properties)
            </span>
          </div>

          {result.properties && result.properties.length > 0 && (
            <div className="border border-border rounded-lg p-4">
              <ScatterChart
                data={result.properties}
                title="Price vs Square Footage"
                xAxis="sqft"
                yAxis="sold_price"
              />
            </div>
          )}

          <div className="border border-border rounded-lg p-4">
            <h4 className="text-sm font-semibold mb-3">Property List History</h4>
            <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
              {result.properties?.map((prop: any, i: number) => (
                <div
                  key={i}
                  className="p-3 bg-secondary/50 rounded-md space-y-1 hover:bg-secondary/70 transition-colors"
                >
                  <p className="text-sm font-medium text-foreground">
                    {prop.address}
                  </p>
                  <div className="flex gap-4 text-xs text-muted-foreground">
                    <span>{prop.beds} bed</span>
                    <span>{prop.baths} bath</span>
                    <span>{prop.sqft?.toLocaleString()} sqft</span>
                  </div>
                  <div className="flex justify-between items-center pt-1">
                    <p className="text-sm font-semibold text-primary">
                      ${(prop.sold_price || prop.price)?.toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      ${prop.price_per_sqft}/sqft
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )
    }

    if (result.type === 'time_series_chart') {
      return (
        <div key={index} className="space-y-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-card-foreground">
              {result.title || 'Trend Analysis'}
            </h3>
          </div>

          <div className="border border-border rounded-lg p-4">
            <TimeSeriesChart
              data={result.data || []}
              title={result.title}
              metric={result.metric || 'value'}
              zipCode={result.zip_code}
            />
          </div>
        </div>
      )
    }

    return (
      <div key={index} className="border border-border rounded-lg p-4">
        <pre className="text-xs overflow-x-auto bg-secondary/30 p-3 rounded">
          {JSON.stringify(result, null, 2)}
        </pre>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-card border-l border-border">
      {/* Header */}
      <div className="p-4 border-b border-border bg-card/80 backdrop-blur-sm shadow-sm sticky top-0 z-10">
        <h2 className="text-lg font-semibold text-card-foreground flex items-center gap-2">
          <Clock className="w-5 h-5" /> History Record
        </h2>
        <p className="text-sm text-muted-foreground">
          Historical query responses and reports
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-8">
        {history.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-3">
              <FileText className="h-12 w-12 text-muted-foreground mx-auto" />
              <p className="text-sm text-muted-foreground max-w-xs">
                History cards will appear here as you ask questions
              </p>
            </div>
          </div>
        ) : (
          history.slice().reverse().map((session, sIdx) => {
             // Extract Agent Analysis block
             const analysisText = session.agentMessages.filter((msg) => msg.trim() !== "").join("\n\n")
             
             return (
              <div key={session.id} className="relative bg-background border border-border rounded-xl shadow-sm p-5 space-y-6">
                 {/* Card Badge */}
                 <div className="absolute -top-3 left-4 bg-primary text-primary-foreground text-xs font-bold px-2 py-1 rounded-full shadow-md">
                    Session {history.length - sIdx}
                 </div>
                 
                 {/* Agent Analysis */}
                 {analysisText && (
                   <div className="space-y-2 mt-2">
                     <h3 className="font-bold text-card-foreground text-sm flex items-center gap-2 text-primary">
                       <TrendingUp className="h-4 w-4" />
                       Agent Analysis
                     </h3>
                     <div className="text-sm text-foreground bg-accent/20 p-4 rounded-lg border border-accent">
                       <ReactMarkdown
                         components={{
                           p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                           ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-2" {...props} />,
                           ol: ({ node, ...props }) => <ol className="list-decimal pl-4 mb-2" {...props} />,
                           li: ({ node, ...props }) => <li className="mb-1" {...props} />,
                           h3: ({ node, ...props }) => <h3 className="font-bold text-lg mb-2 mt-4" {...props} />,
                           h4: ({ node, ...props }) => <h4 className="font-bold mb-1 mt-3" {...props} />,
                           strong: ({ node, ...props }) => <strong className="font-semibold" {...props} />,
                           a: ({ node, ...props }) => <a className="underline hover:opacity-80" target="_blank" rel="noopener noreferrer" {...props} />
                         }}
                       >
                         {analysisText}
                       </ReactMarkdown>
                     </div>
                   </div>
                 )}

                 {/* Tool Results */}
                 <div className="space-y-4">
                   {session.toolResults.map((result, i) => renderToolResult(result, i))}
                 </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
