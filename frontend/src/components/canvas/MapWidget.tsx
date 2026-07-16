// frontend/src/components/canvas/MapWidget.tsx
import { useMemo, useState } from 'react'
import PropertyMap from '../map/PropertyMap'

// result: a comparable_sales tool result ({ zip_code, map_markers, ... })
export default function MapWidget({ result }: { result: any }) {
  const [maxPrice, setMaxPrice] = useState(5000000)
  const [minBeds, setMinBeds] = useState(0)

  const markers = useMemo(() => {
    const raw: any[] = result?.map_markers ?? []
    return raw
      // Null lat/lon renders at (0,0) "Null Island" - drop ungeocodable rows
      .filter(m => typeof m.lat === 'number' && typeof m.lon === 'number'
        && !Number.isNaN(m.lat) && !Number.isNaN(m.lon))
      .filter(m => {
        const price = m.price ?? m.appraised_value ?? 0
        return price <= maxPrice && (m.beds ?? 0) >= minBeds
      })
      .map(m => ({ ...m, price: m.price ?? m.appraised_value }))
  }, [result, maxPrice, minBeds])

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-[220px] p-2">
        <PropertyMap zipCode={result?.zip_code} markers={markers} height="100%" />
      </div>
      <div className="px-3 pb-2 grid grid-cols-2 gap-x-4 flex-shrink-0">
        <div>
          <label className="text-xs text-muted-foreground">
            Max price: ${(maxPrice / 1000).toLocaleString()}K
          </label>
          <input type="range" min="100000" max="5000000" step="50000" value={maxPrice}
            onChange={e => setMaxPrice(parseInt(e.target.value))}
            className="w-full accent-primary h-1.5" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Min beds: {minBeds}+</label>
          <input type="range" min="0" max="5" step="1" value={minBeds}
            onChange={e => setMinBeds(parseInt(e.target.value))}
            className="w-full accent-primary h-1.5" />
        </div>
      </div>
    </div>
  )
}
