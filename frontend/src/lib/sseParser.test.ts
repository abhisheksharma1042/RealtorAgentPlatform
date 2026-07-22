import { describe, it, expect } from 'vitest'
import { createSseParser } from './sseParser'

describe('createSseParser', () => {
  it('parses complete events in a single chunk', () => {
    const feed = createSseParser()
    expect(feed('data: {"type":"complete"}\n\n')).toEqual(['{"type":"complete"}'])
  })

  it('reassembles an event split across chunks (proxy/TLS chunking)', () => {
    const feed = createSseParser()
    const payload = '{"type":"tool_result","result":{"note":"a long string that got split"}}'
    const wire = `data: ${payload}\n\n`
    const first = feed(wire.slice(0, 30))
    const second = feed(wire.slice(30))
    expect(first).toEqual([])
    expect(second).toEqual([payload])
  })

  it('handles multiple events and a partial tail in one chunk', () => {
    const feed = createSseParser()
    const out = feed('data: {"a":1}\n\ndata: {"b":2}\n\ndata: {"c"')
    expect(out).toEqual(['{"a":1}', '{"b":2}'])
    expect(feed(':3}\n')).toEqual(['{"c":3}'])
  })

  it('strips trailing \\r from CRLF-framed lines', () => {
    const feed = createSseParser()
    expect(feed('data: {"a":1}\r\n')).toEqual(['{"a":1}'])
  })

  it('ignores non-data lines (comments, event names, blanks)', () => {
    const feed = createSseParser()
    expect(feed(': keepalive\nevent: ping\n\ndata: {"ok":true}\n')).toEqual(['{"ok":true}'])
  })
})
