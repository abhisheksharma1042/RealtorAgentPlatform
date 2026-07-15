import { useState } from 'react'
import PropertyMap from './PropertyMap'
import { MapPin, Filter, Table, ChevronUp, ChevronDown } from 'lucide-react'

interface MarkerData {
  lat: number
  lon: number
  price?: number | null
  appraised_value?: number | null
  price_kind?: 'sold' | 'appraised' | null
  address?: string
  beds?: number
  baths?: number
  sqft?: number
  year_built?: number
  source?: string
}

interface FiltersAndMapPanelProps {
  latestSales?: {
    zipCode: string
    markers: MarkerData[]
  } | null
  filters?: {
    minPrice: number
    maxPrice: number
    minBeds: number
    minBaths: number
  }
  onFilterChange?: {
    setMinPrice: (val: number) => void
    setMaxPrice: (val: number) => void
    setMinBeds: (val: number) => void
    setMinBaths: (val: number) => void
  }
}

type SortKey = 'price' | 'beds' | 'baths' | 'sqft' | 'address'
type SortDir = 'asc' | 'desc'

export default function FiltersAndMapPanel({ latestSales, filters, onFilterChange }: FiltersAndMapPanelProps) {
  const [sortKey, setSortKey] = useState<SortKey>('price')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const markers = latestSales?.markers ?? []

  // A single "displayable" value per row: sold price if available, else appraised.
  // Texas is non-disclosure so most county-sourced rows only have appraised.
  const displayPrice = (m: MarkerData): number | null => {
    return m.price ?? m.appraised_value ?? null
  }

  const sortedMarkers = [...markers].sort((a, b) => {
    let aVal: number | string = 0
    let bVal: number | string = 0
    if (sortKey === 'price') { aVal = displayPrice(a) ?? 0; bVal = displayPrice(b) ?? 0 }
    else if (sortKey === 'beds') { aVal = a.beds ?? 0; bVal = b.beds ?? 0 }
    else if (sortKey === 'baths') { aVal = a.baths ?? 0; bVal = b.baths ?? 0 }
    else if (sortKey === 'sqft') { aVal = a.sqft ?? 0; bVal = b.sqft ?? 0 }
    else if (sortKey === 'address') { aVal = a.address ?? ''; bVal = b.address ?? '' }
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
    return 0
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp className="h-3 w-3 opacity-20" />
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary" />
      : <ChevronDown className="h-3 w-3 text-primary" />
  }

  const colHeader = (label: string, key: SortKey, align = 'left') => (
    <th
      className={`px-3 py-2 text-xs font-semibold text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors text-${align} whitespace-nowrap`}
      onClick={() => handleSort(key)}
    >
      <span className="inline-flex items-center gap-1">
        {label} <SortIcon col={key} />
      </span>
    </th>
  )

  return (
    <div className="h-full flex flex-col bg-card overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-border flex-shrink-0">
        <h2 className="text-lg font-semibold text-card-foreground flex items-center gap-2">
          <MapPin className="h-5 w-5" />
          Map Workspace
        </h2>
        <p className="text-sm text-muted-foreground">Latest query results</p>
      </div>

      {/* Map — fixed height */}
      <div className="h-56 flex-shrink-0 p-3 pb-0">
        {latestSales ? (
          <PropertyMap zipCode={latestSales.zipCode} markers={latestSales.markers} height="100%" />
        ) : (
          <div className="h-full w-full flex items-center justify-center bg-secondary/20 rounded-lg border border-border">
            <p className="text-muted-foreground text-sm">Ask a question to see properties here.</p>
          </div>
        )}
      </div>

      {/* Data Table */}
      <div className="flex-1 flex flex-col min-h-0 border-t border-border mt-3">
        {/* Table header */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border flex-shrink-0 bg-secondary/10">
          <Table className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">Analysis Data</span>
          {markers.length > 0 && (
            <span className="ml-auto text-xs text-muted-foreground">{markers.length} properties</span>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {sortedMarkers.length > 0 ? (
            <table className="w-full text-sm border-collapse">
              <thead className="sticky top-0 bg-card z-10 shadow-sm">
                <tr className="border-b border-border">
                  {colHeader('Address', 'address')}
                  {colHeader('Price', 'price', 'right')}
                  {colHeader('Beds', 'beds', 'right')}
                  {colHeader('Baths', 'baths', 'right')}
                  {colHeader('Sqft', 'sqft', 'right')}
                  <th className="px-3 py-2 text-xs font-semibold text-muted-foreground text-right whitespace-nowrap">$/sqft</th>
                </tr>
              </thead>
              <tbody>
                {sortedMarkers.map((m, i) => {
                  const price = displayPrice(m)
                  const kind = m.price_kind ?? (m.price ? 'sold' : (m.appraised_value ? 'appraised' : null))
                  const pricePerSqft = price && m.sqft ? Math.round(price / m.sqft) : null
                  return (
                    <tr
                      key={i}
                      className="border-b border-border/50 hover:bg-accent/30 transition-colors"
                    >
                      <td className="px-3 py-2 text-foreground font-medium max-w-[120px] truncate" title={m.address}>
                        {m.address ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {price ? (
                          <span className="inline-flex flex-col items-end leading-tight">
                            <span className="text-primary font-semibold">
                              ${(price / 1000).toFixed(0)}K
                            </span>
                            {kind === 'appraised' && (
                              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                appraised
                              </span>
                            )}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">{m.beds ?? '—'}</td>
                      <td className="px-3 py-2 text-right text-foreground">{m.baths ?? '—'}</td>
                      <td className="px-3 py-2 text-right text-foreground whitespace-nowrap">
                        {m.sqft ? m.sqft.toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap">
                        {pricePerSqft ? `$${pricePerSqft}` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              No data to display yet.
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      {filters && onFilterChange && (
        <div className="p-3 border-t border-border bg-secondary/10 flex-shrink-0 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <Filter className="h-3.5 w-3.5" />
            <span>Refine Results</span>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Max Price: ${(filters.maxPrice / 1000).toLocaleString()}K</label>
              <input
                type="range" min="100000" max="3000000" step="50000"
                value={filters.maxPrice}
                onChange={e => onFilterChange.setMaxPrice(parseInt(e.target.value))}
                className="w-full accent-primary h-1.5"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Min Price: ${(filters.minPrice / 1000).toLocaleString()}K</label>
              <input
                type="range" min="0" max="3000000" step="50000"
                value={filters.minPrice}
                onChange={e => onFilterChange.setMinPrice(parseInt(e.target.value))}
                className="w-full accent-primary h-1.5"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Min Beds: {filters.minBeds}+</label>
              <input
                type="range" min="0" max="5" step="1"
                value={filters.minBeds}
                onChange={e => onFilterChange.setMinBeds(parseInt(e.target.value))}
                className="w-full accent-primary h-1.5"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Min Baths: {filters.minBaths}+</label>
              <input
                type="range" min="0" max="5" step="1"
                value={filters.minBaths}
                onChange={e => onFilterChange.setMinBaths(parseInt(e.target.value))}
                className="w-full accent-primary h-1.5"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

