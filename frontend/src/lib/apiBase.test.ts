import { describe, it, expect } from 'vitest'
import { resolveApiBase } from './apiBase'

describe('resolveApiBase', () => {
  it('defaults to the local backend when VITE_API_URL is unset', () => {
    expect(resolveApiBase({})).toBe('http://localhost:8000')
  })

  it('returns empty string (same-origin) when VITE_API_URL is empty', () => {
    expect(resolveApiBase({ VITE_API_URL: '' })).toBe('')
  })

  it('returns an explicit URL unchanged', () => {
    expect(resolveApiBase({ VITE_API_URL: 'https://api.example.com' })).toBe(
      'https://api.example.com',
    )
  })
})
