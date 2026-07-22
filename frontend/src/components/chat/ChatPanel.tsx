import { useState, useRef, useEffect } from 'react'
import { Send, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { API_BASE } from '../../lib/apiBase'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

// react-markdown passes an internal `node` (hast AST) prop to every component
// override; drop it before spreading the rest onto a DOM element, otherwise
// React warns about an unrecognized `node` attribute.
function stripNode<T extends { node?: unknown }>(props: T): Omit<T, 'node'> {
  const { node, ...rest } = props
  void node
  return rest
}

interface ChatPanelProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- raw SSE tool_result payload; shape varies by tool type
  onToolResult: (result: any) => void
  onStreamComplete: () => void
  injectedMessage?: { text: string; id: number } | null
}

// Suggested prompts for novice users
const SUGGESTED_PROMPTS = [
  "What's the median home price in 75201?",
  "Show me 3BR homes sold in Highland Park",
  "Compare prices between Downtown Dallas and Uptown",
  "What are days on market like in 75205?",
]

export default function ChatPanel({
  onToolResult,
  onStreamComplete,
  injectedMessage,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  // Mirrors `isStreaming` synchronously so handleSendMessage's guard doesn't
  // read a stale closure value when called again right after a stream ends
  // (e.g. flushing a queued injected message from the finally block below).
  const isStreamingRef = useRef(false)
  // Holds an injected message (e.g. a "rerun" click) that arrived while a
  // stream was in flight, so it can be sent once the stream completes.
  const pendingInjectedRef = useRef<string | null>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (messageText?: string) => {
    const text = messageText || input
    if (!text.trim() || isStreamingRef.current) return

    // Add user message
    const userMessage: Message = {
      role: 'user',
      content: text,
      timestamp: new Date(),
    }

    // The assistant response's target position must be derived from `prev`
    // inside this functional update, not from the `messages` closure. A
    // queued rerun (flushed from the FINISHING stream's finally block, see
    // below) invokes handleSendMessage again from a stale closure; if the
    // index were computed from `messages.length` here it would equal the
    // previous turn's index and the new response would overwrite it instead
    // of appending. `assistantIndexRef` is a plain object local to this call
    // of handleSendMessage (not a shared React ref), so concurrent/sequential
    // calls each track their own target index without interfering.
    const assistantIndexRef = { current: -1 }
    setMessages(prev => {
      assistantIndexRef.current = prev.length + 1
      return [...prev, userMessage]
    })
    setInput('')
    setIsStreaming(true)
    isStreamingRef.current = true

    let assistantContent = ''

    try {
      // Connect to SSE endpoint
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: text }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            try {
              const event = JSON.parse(data)

              if (event.type === 'agent_message') {
                // Full message shown in chat — the canvas is *now*, chat scroll
                // is the past.
                assistantContent = event.content.replaceAll('---SUGGESTION---', '\n\n')

                // Update assistant message
                setMessages(prev => {
                  const newMessages = [...prev]
                  const existingIndex = newMessages.findIndex(
                    (m, i) => i === assistantIndexRef.current && m.role === 'assistant'
                  )
                  if (existingIndex >= 0) {
                    newMessages[existingIndex].content = assistantContent
                  } else {
                    newMessages.push({
                      role: 'assistant',
                      content: assistantContent,
                      timestamp: new Date(),
                    })
                  }
                  return newMessages
                })
              } else if (event.type === 'tool_result') {
                onToolResult(event.result)
              } else if (event.type === 'complete') {
                onStreamComplete()
              } else if (event.type === 'error') {
                console.error('Agent error:', event.error)
                setMessages(prev => [
                  ...prev,
                  {
                    role: 'assistant',
                    content: `Error: ${event.error}`,
                    timestamp: new Date(),
                  },
                ])
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error)
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Failed to connect to agent: ${error}`,
          timestamp: new Date(),
        },
      ])
    } finally {
      setIsStreaming(false)
      isStreamingRef.current = false

      // Flush any injected message (e.g. a rerun) that was queued while
      // this stream was active.
      if (pendingInjectedRef.current) {
        const pending = pendingInjectedRef.current
        pendingInjectedRef.current = null
        handleSendMessage(pending)
      }
    }
  }

  useEffect(() => {
    if (injectedMessage?.text) {
      if (isStreamingRef.current) {
        pendingInjectedRef.current = injectedMessage.text
      } else {
        handleSendMessage(injectedMessage.text)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injectedMessage?.id])

  return (
    <div className="h-full flex flex-col bg-card">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <h2 className="text-lg font-semibold text-card-foreground">Chat</h2>
        <p className="text-sm text-muted-foreground">
          Ask questions about DFW real estate
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground mb-3">
              Try asking:
            </p>
            {SUGGESTED_PROMPTS.map((prompt, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(prompt)}
                className="w-full text-left p-3 text-sm rounded-lg border border-border hover:border-primary hover:bg-accent transition-colors"
                disabled={isStreaming}
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        {messages.map((message, i) => (
          <div
            key={i}
            className={`flex ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[80%] rounded-lg p-3 ${
                message.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground'
              }`}
            >
              <div className="text-sm">
                <ReactMarkdown
                  components={{
                    p: (props) => <p className="mb-2 last:mb-0" {...stripNode(props)} />,
                    ul: (props) => <ul className="list-disc pl-4 mb-2" {...stripNode(props)} />,
                    ol: (props) => <ol className="list-decimal pl-4 mb-2" {...stripNode(props)} />,
                    li: (props) => <li className="mb-1" {...stripNode(props)} />,
                    h3: (props) => <h3 className="font-bold text-lg mb-2 mt-4" {...stripNode(props)} />,
                    h4: (props) => <h4 className="font-bold mb-1 mt-3" {...stripNode(props)} />,
                    strong: (props) => <strong className="font-semibold" {...stripNode(props)} />,
                    a: (props) => <a className="underline hover:opacity-80" target="_blank" rel="noopener noreferrer" {...stripNode(props)} />
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
              <p className="text-xs opacity-70 mt-1">
                {message.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}

        {isStreaming && (
          <div className="flex justify-start">
            <div className="bg-secondary text-secondary-foreground rounded-lg p-3">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Ask about DFW real estate..."
            disabled={isStreaming}
            className="flex-1 px-3 py-2 rounded-md border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          <button
            onClick={() => handleSendMessage()}
            disabled={!input.trim() || isStreaming}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
