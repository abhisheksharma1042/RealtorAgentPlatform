// placeholder - replaced in Task 11/12
export default function PropertyCardWidget({ result }: { result: any }) {
  return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
}
