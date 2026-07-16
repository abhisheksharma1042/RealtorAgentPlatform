// frontend/src/components/hermes/HermesKnowsPanel.tsx
/* eslint-disable @typescript-eslint/no-explicit-any */
// TODO(types): discriminated union for pin/search/skill/coverage memory-api rows
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { X, Trash2, Play, Brain, MapPinned } from 'lucide-react'
import {
  getPins, deletePin, getSearches, deleteSearch,
  getSkills, setSkillLevel, deleteSkill, getCoverage,
} from '../../lib/memoryApi'

interface HermesKnowsPanelProps {
  open: boolean
  onClose: () => void
  version: number                 // bump to refetch (memory changed elsewhere)
  onRerunSearch: (name: string) => void
  onShowCoverage: () => void
  onMemoryChange?: () => void     // notify the canvas after a mutation here
}

const LEVELS = ['novice', 'learning', 'familiar'] as const

function Section({ title, error, onRetry, children }: {
  title: string; error: boolean; onRetry: () => void; children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {error
        ? <button onClick={onRetry} className="text-xs text-destructive underline">Failed to load — retry</button>
        : children}
    </div>
  )
}

export default function HermesKnowsPanel({
  open, onClose, version, onRerunSearch, onShowCoverage, onMemoryChange,
}: HermesKnowsPanelProps) {
  const [pins, setPins] = useState<any[] | null>(null)
  const [searches, setSearches] = useState<any[] | null>(null)
  const [skills, setSkills] = useState<any[] | null>(null)
  const [coverage, setCoverage] = useState<any | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    if (!open) return
    getPins().then(setPins).catch(() => setPins(null))
    getSearches().then(setSearches).catch(() => setSearches(null))
    getSkills().then(setSkills).catch(() => setSkills(null))
    getCoverage().then(setCoverage).catch(() => setCoverage(null))
  }, [open, version, reload])

  if (!open) return null
  const retry = () => setReload(r => r + 1)

  // memoryApi mutation calls reject on non-2xx responses; without a .catch,
  // a failed mutation becomes an unhandled rejection and the triggering
  // button silently does nothing. Always refetch afterward so the UI stays
  // in sync with server truth even on failure.
  const mutate = (p: Promise<unknown>) => p.then(retry).catch(err => {
    console.error('memory mutation failed', err)
    retry()
  }).then(() => onMemoryChange?.())

  return (
    <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-card border-l border-border shadow-xl z-50 flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Brain className="h-4 w-4" /> Hermes Knows
        </h2>
        <button onClick={onClose} aria-label="Close panel"
                className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <Section title="Saved searches" error={searches === null} onRetry={retry}>
          {searches?.length === 0 && (
            <p className="text-xs text-muted-foreground">None yet — ask Hermes to save one.</p>
          )}
          {searches?.map((s: any) => (
            <div key={s.name} className="border border-border rounded-lg p-2 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium">{s.name}</span>
                <span className="flex gap-2">
                  <button onClick={() => { onRerunSearch(s.name); onClose() }}
                          aria-label={`Rerun ${s.name}`}
                          className="text-muted-foreground hover:text-primary">
                    <Play className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => mutate(deleteSearch(s.name))}
                          aria-label={`Delete ${s.name}`}
                          className="text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {Object.entries(s.criteria ?? {}).map(([k, v]) => `${k}=${v}`).join(' · ')}
              </p>
              {s.client_note && (
                <p className="text-xs italic text-muted-foreground">"{s.client_note}"</p>
              )}
            </div>
          ))}
        </Section>

        <Section title="Pinned properties" error={pins === null} onRetry={retry}>
          {pins?.length === 0 && (
            <p className="text-xs text-muted-foreground">Nothing pinned yet.</p>
          )}
          {pins?.map((p: any) => (
            <div key={p.property_id} className="border border-border rounded-lg p-2 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium truncate">{p.properties?.address ?? p.property_id}</span>
                <button onClick={() => mutate(deletePin(p.property_id))}
                        aria-label="Unpin"
                        className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              {p.note && <p className="text-xs italic text-muted-foreground">"{p.note}"</p>}
            </div>
          ))}
        </Section>

        <Section title="Your skill profile" error={skills === null} onRetry={retry}>
          {skills?.length === 0 && (
            <p className="text-xs text-muted-foreground">Hermes hasn't observed anything yet.</p>
          )}
          {skills?.map((s: any) => (
            <div key={s.concept}
                 className="flex items-center justify-between text-sm border-b border-border/40 py-1">
              <span>{s.concept}</span>
              <span className="flex items-center gap-2">
                <select value={s.level}
                        aria-label={`Level for ${s.concept}`}
                        onChange={e => mutate(setSkillLevel(s.concept, e.target.value))}
                        className="text-xs bg-secondary rounded px-1 py-0.5 border border-border">
                  {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
                <button onClick={() => mutate(deleteSkill(s.concept))}
                        aria-label={`Forget ${s.concept}`}
                        className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            </div>
          ))}
        </Section>

        <Section title="Data coverage" error={coverage === null} onRetry={retry}>
          {coverage && (
            <div className="text-xs text-muted-foreground space-y-1">
              <p>
                {[...new Set(coverage.coverage.map((r: any) => r.county))].join(', ')} ·{' '}
                {coverage.coverage.length} zips ·{' '}
                {coverage.coverage
                  .reduce((n: number, r: any) => n + (r.parcel_count ?? 0), 0)
                  .toLocaleString()} parcels
              </p>
              <button onClick={() => { onShowCoverage(); onClose() }}
                      className="inline-flex items-center gap-1 text-primary hover:underline">
                <MapPinned className="h-3 w-3" /> View coverage map
              </button>
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}
