import { useState, useMemo } from 'react'
import ChatPanel from './components/chat/ChatPanel'
import FiltersAndMapPanel from './components/map/FiltersAndMapPanel'
import OutputPanel from './components/output/OutputPanel'
import './index.css'

export interface QuerySession {
  id: string
  agentMessages: string[]
  toolResults: any[]
}

function App() {
  const [history, setHistory] = useState<QuerySession[]>([])
  
  // Filters State
  const [minPrice, setMinPrice] = useState<number>(0)
  const [maxPrice, setMaxPrice] = useState<number>(3000000)
  const [minBeds, setMinBeds] = useState<number>(0)
  const [minBaths, setMinBaths] = useState<number>(0)
  
  const handleStreamStart = () => {
    // Start a new session in history
    setHistory(prev => [
      ...prev,
      { id: Date.now().toString(), agentMessages: [], toolResults: [] }
    ])
  }

  // NOTE: These updaters MUST be pure (no mutation). React StrictMode invokes
  // functional updaters twice in dev - if we mutate nested arrays via .push,
  // entries get appended twice and the history cards render duplicated
  // Agent Analysis and Tool Result widgets.
  const handleToolResult = (result: any) => {
    setHistory(prev => {
      if (prev.length === 0) return prev
      const lastIdx = prev.length - 1
      return prev.map((s, i) =>
        i === lastIdx
          ? { ...s, toolResults: [...s.toolResults, result] }
          : s
      )
    })
  }

  const handleAgentMessage = (message: string) => {
    setHistory(prev => {
      if (prev.length === 0) return prev
      const lastIdx = prev.length - 1
      return prev.map((s, i) =>
        i === lastIdx
          ? { ...s, agentMessages: [...s.agentMessages, message] }
          : s
      )
    })
  }

  const handleStreamComplete = () => {
    console.log('Stream complete')
  }
  
  // Extract latest comparable sales for the Center Map
  const latestComparableSales = useMemo(() => {
     if (history.length === 0) return null;
     const currentSession = history[history.length - 1];
     // Find the last comparable_sales tool result
     const salesTool = [...currentSession.toolResults].reverse().find(r => r.type === 'comparable_sales');
     return salesTool || null;
  }, [history]);
  
  // Apply local filters dynamically
  const filteredLatestSales = useMemo(() => {
      if (!latestComparableSales || !latestComparableSales.properties) return null;
      
      const filteredProps = latestComparableSales.properties.filter((prop: any) => {
         const price = prop.sold_price || prop.price || 0;
         const beds = prop.beds || 0;
         const baths = prop.baths || 0;
         
         const priceOk = price >= minPrice && price <= maxPrice;
         const bedsOk = beds >= minBeds;
         const bathsOk = baths >= minBaths;
         
         return priceOk && bedsOk && bathsOk;
      });
      
      const formattedMarkers = filteredProps.map((p: any) => ({
          lat: p.lat,
          lon: p.lon,
          price: p.sold_price || p.price,
          address: p.address,
          beds: p.beds,
          baths: p.baths,
          sqft: p.sqft
      }));
      
      return {
          zipCode: latestComparableSales.zip_code,
          markers: formattedMarkers
      }
  }, [latestComparableSales, minPrice, maxPrice, minBeds, minBaths]);

  return (
    <div className="h-screen w-screen bg-background">
      {/* Header */}
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">
              DFW Realtor Agent
            </h1>
            <p className="text-sm text-muted-foreground">
              AI-powered real estate research for Dallas-Fort Worth
            </p>
          </div>
        </div>
      </header>

      {/* Three-pane layout - Simple grid for now, resizable panels in Phase 9 */}
      <div className="h-[calc(100vh-73px)] grid grid-cols-12 gap-1">
        {/* Left: Chat Panel */}
        <div className="col-span-3 overflow-hidden">
          <ChatPanel
            onStreamStart={handleStreamStart}
            onToolResult={handleToolResult}
            onAgentMessage={handleAgentMessage}
            onStreamComplete={handleStreamComplete}
          />
        </div>

        {/* Center: Filters and Map */}
        <div className="col-span-4 border-l border-r border-border overflow-hidden">
          <FiltersAndMapPanel 
             latestSales={filteredLatestSales} 
             filters={{ minPrice, maxPrice, minBeds, minBaths }}
             onFilterChange={{ setMinPrice, setMaxPrice, setMinBeds, setMinBaths }}
          />
        </div>

        {/* Right: Output Panel */}
        <div className="col-span-5 overflow-hidden">
          <OutputPanel history={history} />
        </div>
      </div>
    </div>
  )
}

export default App
