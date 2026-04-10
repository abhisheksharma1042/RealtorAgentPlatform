import { useState, useMemo } from 'react'
import { MapPin } from 'lucide-react'
import Map, { Marker, Popup } from 'react-map-gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'

interface MapMarker {
  lat: number
  lon: number
  price?: number
  address?: string
  beds?: number
  baths?: number
  sqft?: number
}

interface PropertyMapProps {
  markers?: MapMarker[]
  zipCode?: string
  height?: string
}

// ZIP code centers
const ZIP_CENTERS: Record<string, { name: string }> = {
  '75201': { name: 'Downtown Dallas' },
  '75205': { name: 'Highland Park' },
  '75219': { name: 'Uptown Dallas' },
  '75024': { name: 'Plano' },
  '75025': { name: 'West Plano' },
  '75034': { name: 'Frisco' },
}

export default function PropertyMap({
  markers = [],
  zipCode,
  height = '500px',
}: PropertyMapProps) {
  const [selectedMarker, setSelectedMarker] = useState<MapMarker | null>(null)
  
  const mapboxToken = import.meta.env.VITE_MAPBOX_TOKEN;

  const initialViewState = useMemo(() => {
    if (markers.length === 0) return { longitude: -96.7970, latitude: 32.7767, zoom: 10 }; // DFW default
    
    const minLon = Math.min(...markers.map(m => m.lon));
    const maxLon = Math.max(...markers.map(m => m.lon));
    const minLat = Math.min(...markers.map(m => m.lat));
    const maxLat = Math.max(...markers.map(m => m.lat));
    
    // Calculate center
    const longitude = (minLon + maxLon) / 2;
    const latitude = (minLat + maxLat) / 2;
    
    // Approximate zoom calculation
    const latDiff = maxLat - minLat;
    const lonDiff = maxLon - minLon;
    const maxDiff = Math.max(latDiff, lonDiff);
    let zoom = 12;
    if (maxDiff > 0) {
       zoom = Math.floor(8 - Math.log2(maxDiff));
       zoom = Math.max(9, Math.min(zoom, 14)); // clamp between 9 and 14
    }
    
    return {
      longitude,
      latitude,
      zoom
    };
  }, [markers]);

  // Fallback to List View if no mapbox token
  if (!mapboxToken) {
    return (
      <div
        className="w-full bg-secondary/20 rounded-lg flex flex-col p-6"
        style={{ height }}
      >
        <div className="flex items-center gap-2 mb-4">
          <MapPin className="h-5 w-5 text-primary" />
          <div>
            <h3 className="font-semibold text-foreground">
              {zipCode && ZIP_CENTERS[zipCode]
                ? ZIP_CENTERS[zipCode].name
                : 'DFW Area'}
            </h3>
            {zipCode && (
              <p className="text-sm text-muted-foreground">ZIP: {zipCode}</p>
            )}
          </div>
        </div>

        {/* Property Markers List */}
        {markers.length > 0 ? (
          <div className="flex-1 overflow-y-auto space-y-2">
            <p className="text-sm text-muted-foreground mb-3">
              {markers.length} properties
            </p>
            {markers.map((marker, idx) => (
              <div
                key={idx}
                onClick={() => setSelectedMarker(marker)}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedMarker === marker
                    ? 'border-primary bg-primary/10'
                    : 'border-border bg-card hover:border-primary/50'
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">
                      {marker.address || `Property ${idx + 1}`}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Lat: {marker.lat.toFixed(4)}, Lon: {marker.lon.toFixed(4)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-semibold text-primary">
                      ${marker.price ? (marker.price / 1000).toFixed(0) : '?'}K
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-2">
              <MapPin className="h-12 w-12 text-muted-foreground mx-auto" />
              <p className="text-sm text-muted-foreground">
                No properties to display
              </p>
            </div>
          </div>
        )}

        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground text-center">
            📍 Interactive Mapbox integration available. Add VITE_MAPBOX_TOKEN to .env.local
          </p>
        </div>
      </div>
    )
  }

  // Interactive Map View
  return (
    <div className="w-full relative rounded-lg overflow-hidden border border-border" style={{ height }}>
      <Map
        mapboxAccessToken={mapboxToken}
        initialViewState={initialViewState}
        mapStyle="mapbox://styles/mapbox/streets-v12"
      >
        {markers.map((marker, index) => (
          <Marker
            key={index}
            longitude={marker.lon}
            latitude={marker.lat}
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              setSelectedMarker(marker);
            }}
          >
            <div className="flex items-center justify-center bg-primary rounded-full px-2 py-1 shadow-md cursor-pointer border-2 border-background text-primary-foreground transform hover:scale-110 transition-transform">
              <span className="text-xs font-bold">
                ${marker.price ? (marker.price / 1000).toFixed(0) : '?'}K
              </span>
            </div>
          </Marker>
        ))}

        {selectedMarker && (
          <Popup
            longitude={selectedMarker.lon}
            latitude={selectedMarker.lat}
            anchor="bottom"
            onClose={() => setSelectedMarker(null)}
            closeOnClick={false}
            className="rounded-lg shadow-xl"
          >
            <div className="p-3 text-sm text-foreground bg-background space-y-2 w-48">
              <h4 className="font-bold border-b pb-1 truncate">{selectedMarker.address || "Property Address"}</h4>
              <p className="text-primary font-semibold text-lg">
                ${selectedMarker.price?.toLocaleString()}
              </p>
              {(selectedMarker.beds || selectedMarker.sqft) && (
                 <div className="flex gap-2 text-xs text-muted-foreground">
                    {selectedMarker.beds && <span>{selectedMarker.beds} bd</span>}
                    {selectedMarker.baths && <span>{selectedMarker.baths} ba</span>}
                    {selectedMarker.sqft && <span>{selectedMarker.sqft} sqft</span>}
                 </div>
              )}
            </div>
          </Popup>
        )}
      </Map>
      
      {/* Map absolute HUD */}
      {zipCode && ZIP_CENTERS[zipCode] && (
        <div className="absolute top-4 left-4 bg-background/90 backdrop-blur-sm p-3 rounded-lg shadow-md border border-border z-10">
          <h3 className="font-semibold text-foreground text-sm">{ZIP_CENTERS[zipCode].name}</h3>
          <p className="text-xs text-muted-foreground">ZIP: {zipCode} ({markers.length} properties)</p>
        </div>
      )}
    </div>
  )
}
