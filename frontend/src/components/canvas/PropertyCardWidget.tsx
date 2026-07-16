// frontend/src/components/canvas/PropertyCardWidget.tsx
export default function PropertyCardWidget({ result }: { result: any }) {
  const p = result?.property ?? {}
  const price = p.sold_price ?? p.price
  const rows: Array<[string, any]> = [
    ['Beds', p.beds], ['Baths', p.baths],
    ['Sqft', p.sqft?.toLocaleString()], ['Year built', p.year_built],
    ['Zip', p.zip_code], ['Source', p.source],
  ]
  return (
    <div className="p-4 space-y-3">
      <div>
        <p className="font-semibold text-foreground">{p.address ?? 'Unknown address'}</p>
        {result?.note && <p className="text-xs text-muted-foreground italic">"{result.note}"</p>}
      </div>
      <div>
        {price ? (
          <p className="text-xl font-bold text-primary">
            ${Number(price).toLocaleString()}{' '}
            <span className="text-xs font-normal text-muted-foreground">sold</span>
          </p>
        ) : p.appraised_value ? (
          <p className="text-xl font-bold text-primary">
            ${Number(p.appraised_value).toLocaleString()}{' '}
            <span className="text-xs font-normal text-muted-foreground uppercase">appraised</span>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No price data</p>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {rows.filter(([, v]) => v != null).map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-border/40 py-0.5">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="text-foreground font-medium">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
