// frontend/src/lib/sseParser.ts
// Incremental SSE line parser. Network reads do NOT arrive aligned to event
// boundaries — proxies and TLS re-chunk the stream — so a partial line must be
// buffered until its terminating newline arrives in a later chunk. Feed it raw
// decoded text; it returns the payload of each *complete* `data: ` line.
export function createSseParser(): (chunk: string) => string[] {
  let buffer = ''
  return (chunk: string) => {
    buffer += chunk
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    return lines
      .map(line => (line.endsWith('\r') ? line.slice(0, -1) : line))
      .filter(line => line.startsWith('data: '))
      .map(line => line.slice(6))
  }
}
