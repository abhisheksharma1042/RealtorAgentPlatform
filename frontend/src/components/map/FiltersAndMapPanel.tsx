import PropertyMap from './PropertyMap'
import { MapPin, Filter } from 'lucide-react'

interface FiltersAndMapPanelProps {
  latestSales?: {
    zipCode: string
    markers: any[]
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

export default function FiltersAndMapPanel({ latestSales, filters, onFilterChange }: FiltersAndMapPanelProps) {
  return (
    <div className="h-full flex flex-col bg-card">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <h2 className="text-lg font-semibold text-card-foreground flex items-center gap-2">
          <MapPin className="h-5 w-5" />
          Map Workspace
        </h2>
        <p className="text-sm text-muted-foreground">Latest query results</p>
      </div>

      {/* Map */}
      <div className="flex-1 p-4 overflow-hidden">
        {latestSales ? (
           <PropertyMap zipCode={latestSales.zipCode} markers={latestSales.markers} height="100%" />
        ) : (
           <div className="h-full w-full flex items-center justify-center bg-secondary/20 rounded-lg border border-border">
              <p className="text-muted-foreground text-sm">Ask a question to see properties here.</p>
           </div>
        )}
      </div>

      {/* Filters */}
      {filters && onFilterChange && (
        <div className="p-4 border-t border-border bg-secondary/10 space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold mb-2">
            <Filter className="h-4 w-4" />
            <span>Refine Results</span>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
             <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Price: ${(filters.maxPrice / 1000).toLocaleString()}K</label>
                <input 
                   type="range" 
                   min="100000" 
                   max="3000000" 
                   step="50000"
                   value={filters.maxPrice} 
                   onChange={e => onFilterChange.setMaxPrice(parseInt(e.target.value))}
                   className="w-full accent-primary" 
                />
             </div>
             
             <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Min Price: ${(filters.minPrice / 1000).toLocaleString()}K</label>
                <input 
                   type="range" 
                   min="0" 
                   max="3000000" 
                   step="50000"
                   value={filters.minPrice} 
                   onChange={e => onFilterChange.setMinPrice(parseInt(e.target.value))}
                   className="w-full accent-primary" 
                />
             </div>

             <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Min Beds: {filters.minBeds}+</label>
                <input 
                   type="range" 
                   min="0" 
                   max="5" 
                   step="1"
                   value={filters.minBeds} 
                   onChange={e => onFilterChange.setMinBeds(parseInt(e.target.value))}
                   className="w-full accent-primary" 
                />
             </div>
             
             <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Min Baths: {filters.minBaths}+</label>
                <input 
                   type="range" 
                   min="0" 
                   max="5" 
                   step="1"
                   value={filters.minBaths} 
                   onChange={e => onFilterChange.setMinBaths(parseInt(e.target.value))}
                   className="w-full accent-primary" 
                />
             </div>
          </div>
        </div>
      )}
    </div>
  )
}
