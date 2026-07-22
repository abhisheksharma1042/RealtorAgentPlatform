// frontend/src/lib/memoryApi.ts
import { API_BASE } from './apiBase'

const BASE = `${API_BASE}/api`

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path}: ${res.status}`)
  return res.json()
}

export const getPins = () => req('/memory/pins')
export const createPin = (propertyId: string, note?: string) =>
  req('/memory/pins', { method: 'POST', body: JSON.stringify({ property_id: propertyId, note }) })
export const deletePin = (propertyId: string) =>
  req(`/memory/pins/${propertyId}`, { method: 'DELETE' })

export const getSearches = () => req('/memory/searches')
export const deleteSearch = (name: string) =>
  req(`/memory/searches/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const getSkills = () => req('/memory/skills')
export const setSkillLevel = (concept: string, level: string) =>
  req(`/memory/skills/${encodeURIComponent(concept)}`, { method: 'PUT', body: JSON.stringify({ level }) })
export const deleteSkill = (concept: string) =>
  req(`/memory/skills/${encodeURIComponent(concept)}`, { method: 'DELETE' })

export const getCoverage = () => req('/coverage')
