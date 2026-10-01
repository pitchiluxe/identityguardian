import { useCallback, useEffect, useState } from 'react';

export type Session = { user: { id: string; name: string }; organizations: { id: string; name: string }[]; csrf_token: string; amr: string[]; auth_time: number };
export type Overview = { organization: { name: string }; environments: { id: string; name: string; kind: string }[]; member_count: number; roles: string[]; capabilities: string[]; identity_data: string };
export type Environment = { id: string; name: string; kind: string; last_sync: string | null };
export type SnapshotInfo = { effective_at: string; known_at: string; graph_version: string };
export type Envelope<T> = { data: T; correlation_id: string; snapshot?: SnapshotInfo; completeness?: string; evidence_ids?: string[]; next_cursor?: string | null; [key: string]: unknown };
export type TwinNode = { id: string; external_id: string; kind: string; subtype: string; name: string; status: string; attributes: Record<string, unknown> };
export type TwinEdge = { id: string; relationship_id: string; type: string; classification: string; src: string; dst: string; attributes: Record<string, unknown>; valid_from: string; valid_to: string | null; evidence_id: string; end_inferred: boolean };

export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }

export async function api<T>(path: string, method = 'GET', body?: unknown, csrf?: string): Promise<T> {
  const response = await fetch('/api/v1' + path, { method, credentials: 'same-origin',
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined });
  const type = response.headers.get('content-type') || '';
  const data = type.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === 'object' && data && 'detail' in data ? (data as { detail: unknown }).detail : null;
    throw new ApiError(response.status === 401 ? 'Sign in to continue' : typeof detail === 'string' ? detail : response.status === 422 ? 'Check the requested values and try again.' : `Request failed (${response.status})`, response.status);
  }
  return data as T;
}

/** Loads a GET resource with distinct loading, denied, failed and loaded states. */
export function useResource<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); return; }
    let live = true; setLoading(true); setError(null);
    api<T>(path).then(v => { if (live) setData(v); }).catch(e => { if (live) { setData(null); setError(e as ApiError); } }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  const reload = useCallback(() => setTick(v => v + 1), []);
  return { data, error, loading, reload };
}

export type Ctx = { org: string; env: string; session: Session; can: (capability: string) => boolean; base: string; envKind: string; navigate: (page: string, params?: Record<string, string>) => void; params: Record<string, string> };

export const fmt = (value: unknown) => value === null || value === undefined || value === '' ? '—' : typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) ? new Date(value).toISOString().replace('T', ' ').slice(0, 16) + ' UTC' : typeof value === 'object' ? JSON.stringify(value) : String(value);
export const label = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/^./, c => c.toUpperCase());
