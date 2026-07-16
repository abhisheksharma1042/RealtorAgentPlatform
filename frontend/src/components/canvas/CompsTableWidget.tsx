// placeholder - replaced in Task 11
export default function CompsTableWidget(
  { result }: { result: any; onMemoryChange: () => void },
) {
  return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
}
