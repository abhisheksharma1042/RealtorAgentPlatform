// frontend/src/lib/apiBase.ts
type EnvLike = { VITE_API_URL?: string }

// '' (empty string) is a valid, meaningful value: same-origin. The production
// build sets VITE_API_URL='' so all calls hit /api/* on the current domain and
// the reverse proxy routes them to the backend container.
export function resolveApiBase(env: EnvLike): string {
  return env.VITE_API_URL ?? 'http://localhost:8000'
}

export const API_BASE = resolveApiBase(import.meta.env as EnvLike)
