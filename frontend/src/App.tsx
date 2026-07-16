import { useReducer, useState } from 'react'
import ChatPanel from './components/chat/ChatPanel'
import WidgetCanvas from './components/canvas/WidgetCanvas'
import HermesKnowsPanel from './components/hermes/HermesKnowsPanel'
import { widgetReducer } from './widgets/widgetReducer'
import { toolResultToActions } from './widgets/toolResultToWidgets'
import { getCoverage } from './lib/memoryApi'
import { Brain, MapPinned } from 'lucide-react'
import './index.css'

function App() {
  const [widgets, dispatch] = useReducer(widgetReducer, [])
  const [hermesOpen, setHermesOpen] = useState(false)
  const [memoryVersion, setMemoryVersion] = useState(0)
  const [injectedMessage, setInjectedMessage] =
    useState<{ text: string; id: number } | null>(null)

  const bumpMemory = () => setMemoryVersion(v => v + 1)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw SSE tool_result payload; shape varies by tool type
  const handleToolResult = (result: any) => {
    for (const action of toolResultToActions(result, Date.now())) dispatch(action)
    if (result?.type === 'pin_update' || result?.type === 'saved_search_update'
        || result?.type === 'skill_update') {
      bumpMemory()
    }
  }

  // Skill observations may land silently during a turn - refresh after each stream.
  const handleStreamComplete = () => bumpMemory()

  const handleRerunSearch = (name: string) =>
    setInjectedMessage({ text: `Run my saved search "${name}"`, id: Date.now() })

  const handleShowCoverage = async () => {
    try {
      const cov = await getCoverage()
      dispatch({
        type: 'upsert',
        widget: {
          key: 'coverage', type: 'coverage_map', title: 'Data coverage',
          props: {
            type: 'data_coverage',
            notes: 'Texas is a non-disclosure state: sold prices exist only for the '
              + 'RentCast-sourced subset; DCAD appraised values are public.',
            ...cov,
          },
          updatedAt: Date.now(),
        },
      })
    } catch (e) {
      console.error('coverage fetch failed', e)
    }
  }

  return (
    <div className="h-screen w-screen bg-background">
      <header className="border-b border-border px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">DFW Realtor Agent</h1>
            <p className="text-xs text-muted-foreground">
              Hermes — your market research control center
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleShowCoverage}
                    className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-border hover:bg-accent transition-colors">
              <MapPinned className="h-4 w-4" /> Coverage
            </button>
            <button onClick={() => setHermesOpen(true)}
                    className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-border hover:bg-accent transition-colors">
              <Brain className="h-4 w-4" /> Hermes Knows
            </button>
          </div>
        </div>
      </header>

      <div className="h-[calc(100vh-61px)] grid grid-cols-12">
        <div className="col-span-4 xl:col-span-3 border-r border-border overflow-hidden">
          <ChatPanel
            onToolResult={handleToolResult}
            onStreamComplete={handleStreamComplete}
            injectedMessage={injectedMessage}
          />
        </div>
        <div className="col-span-8 xl:col-span-9 overflow-hidden">
          <WidgetCanvas widgets={widgets} dispatch={dispatch} onMemoryChange={bumpMemory}
                        memoryVersion={memoryVersion} />
        </div>
      </div>

      <HermesKnowsPanel
        open={hermesOpen}
        onClose={() => setHermesOpen(false)}
        version={memoryVersion}
        onRerunSearch={handleRerunSearch}
        onShowCoverage={handleShowCoverage}
        onMemoryChange={bumpMemory}
      />
    </div>
  )
}

export default App
