import { useMemo } from 'react'
import Map, { Source, Layer } from 'react-map-gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Feature } from 'geojson'

interface CoverageRow {
  zip: string
  county?: string
  parcel_count?: number
  sold_listing_count?: number
  stats_to?: string
  appraisal_year?: number
}

// result: a data_coverage tool result ({ coverage: rows, boundaries: [GeoJSON Feature] })
export default function CoverageMapWidget(
  { result }: { result: { coverage?: CoverageRow[]; boundaries?: Feature[]; notes?: string } | null | undefined },
) {
  const mapboxToken = import.meta.env.VITE_MAPBOX_TOKEN
  const rows: CoverageRow[] = result?.coverage ?? []
  const features = useMemo(() => result?.boundaries ?? [], [result?.boundaries])

  const fc = useMemo(
    () => ({ type: 'FeatureCollection' as const, features }),
    [features],
  )

  return (
    <div className="flex flex-col h-full">
      {mapboxToken && features.length > 0 && (
        <div className="h-52 flex-shrink-0 p-2">
          <div className="h-full rounded-lg overflow-hidden border border-border">
            <Map
              mapboxAccessToken={mapboxToken}
              initialViewState={{ longitude: -96.79, latitude: 32.85, zoom: 9.5 }}
              mapStyle="mapbox://styles/mapbox/light-v11"
            >
              <Source id="coverage-zips" type="geojson" data={fc}>
                <Layer id="coverage-fill" type="fill"
                       paint={{ 'fill-color': '#3b82f6', 'fill-opacity': 0.2 }} />
                <Layer id="coverage-line" type="line"
                       paint={{ 'line-color': '#3b82f6', 'line-width': 2 }} />
              </Source>
            </Map>
          </div>
        </div>
      )}
      <div className="p-3 flex-1 overflow-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="text-left py-1 px-2">Zip</th>
              <th className="text-right py-1 px-2">Parcels</th>
              <th className="text-right py-1 px-2">Sold listings</th>
              <th className="text-right py-1 px-2">Stats through</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.zip} className="border-b border-border/40">
                <td className="py-1 px-2 font-medium">
                  {r.zip} <span className="text-muted-foreground">({r.county})</span>
                </td>
                <td className="py-1 px-2 text-right">{r.parcel_count?.toLocaleString()}</td>
                <td className="py-1 px-2 text-right">{r.sold_listing_count ?? 0}</td>
                <td className="py-1 px-2 text-right">{r.stats_to ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-muted-foreground mt-2">
          {rows[0]?.appraisal_year} appraisal roll. {result?.notes}
        </p>
      </div>
    </div>
  )
}
