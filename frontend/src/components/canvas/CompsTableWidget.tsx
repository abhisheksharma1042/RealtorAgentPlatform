// frontend/src/components/canvas/CompsTableWidget.tsx
import { useState } from 'react'
import { ChevronUp, ChevronDown, Pin } from 'lucide-react'
import { createPin } from '../../lib/memoryApi'

type SortKey = 'price' | 'beds' | 'baths' | 'sqft' | 'address'
type SortDir = 'asc' | 'desc'

// Texas is non-disclosure: most county rows only have appraised_value.
const displayPrice = (p: any): number | null =>
  p.sold_price ?? p.price ?? p.appraised_value ?? null

export default function CompsTableWidget(
  { result, onMemoryChange }: { result: any; onMemoryChange: () => void },
) {
  const [sortKey, setSortKey] = useState<SortKey>('price')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [pinned, setPinned] = useState<Set<string>>(new Set())

  const rows: any[] = [...(result?.properties ?? [])].sort((a, b) => {
    const val = (p: any) =>
      sortKey === 'price' ? (displayPrice(p) ?? 0)
      : sortKey === 'address' ? (p.address ?? '')
      : (p[sortKey] ?? 0)
    const [av, bv] = [val(a), val(b)]
    return (av < bv ? -1 : av > bv ? 1 : 0) * (sortDir === 'asc' ? 1 : -1)
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  const handlePin = async (p: any) => {
    try {
      await createPin(p.id)
      setPinned(prev => new Set(prev).add(p.id))
      onMemoryChange()
    } catch (e) {
      console.error('pin failed', e)
    }
  }

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th onClick={() => handleSort(k)}
        className="px-2 py-2 text-xs font-semibold text-muted-foreground cursor-pointer select-none hover:text-foreground whitespace-nowrap text-left">
      <span className="inline-flex items-center gap-1">
        {label}
        {sortKey === k
          ? (sortDir === 'asc'
              ? <ChevronUp className="h-3 w-3 text-primary" />
              : <ChevronDown className="h-3 w-3 text-primary" />)
          : <ChevronUp className="h-3 w-3 opacity-20" />}
      </span>
    </th>
  )

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No matching properties.</p>
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead className="sticky top-0 bg-card z-10 shadow-sm">
        <tr className="border-b border-border">
          <Th label="Address" k="address" />
          <Th label="Price" k="price" />
          <Th label="Beds" k="beds" />
          <Th label="Baths" k="baths" />
          <Th label="Sqft" k="sqft" />
          <th className="px-2 py-2 text-xs font-semibold text-muted-foreground">Pin</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p: any) => {
          const price = displayPrice(p)
          const appraisedOnly = !p.sold_price && !p.price && p.appraised_value
          return (
            <tr key={p.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
              <td className="px-2 py-1.5 font-medium max-w-[140px] truncate" title={p.address}>
                {p.address ?? '—'}
              </td>
              <td className="px-2 py-1.5 whitespace-nowrap">
                {price ? (
                  <span className="inline-flex flex-col leading-tight">
                    <span className="text-primary font-semibold">${(price / 1000).toFixed(0)}K</span>
                    {appraisedOnly && (
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">appraised</span>
                    )}
                  </span>
                ) : '—'}
              </td>
              <td className="px-2 py-1.5">{p.beds ?? '—'}</td>
              <td className="px-2 py-1.5">{p.baths ?? '—'}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{p.sqft ? p.sqft.toLocaleString() : '—'}</td>
              <td className="px-2 py-1.5">
                <button onClick={() => handlePin(p)} disabled={pinned.has(p.id)}
                        aria-label={`Pin ${p.address}`}
                        className={pinned.has(p.id)
                          ? 'text-primary'
                          : 'text-muted-foreground hover:text-primary transition-colors'}>
                  <Pin className="h-3.5 w-3.5" fill={pinned.has(p.id) ? 'currentColor' : 'none'} />
                </button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
