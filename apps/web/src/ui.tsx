import type { ReactNode } from 'react';
import { AlertTriangle, Info, Loader2, ShieldCheck, ShieldX } from 'lucide-react';
import type { ApiError, SnapshotInfo } from './api';
import { fmt } from './api';

export function Empty({ title, text }: { title: string; text: string }) {
  return <section className="empty panel"><ShieldCheck size={32}/><h2>{title}</h2><p>{text}</p></section>;
}

export function Panel({ title, meta, children, actions }: { title: string; meta?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return <section className="panel"><div className="section-heading"><h2>{title}</h2><div className="heading-meta">{meta && <span>{meta}</span>}{actions}</div></div>{children}</section>;
}

/** Distinct loading / denied / failed states. Renders children only with data. */
export function State<T>({ data, error, loading, children, empty }: { data: T | null; error: ApiError | null; loading: boolean; children: (d: T) => ReactNode; empty?: string }) {
  if (error) return error.status === 403 ? <div className="state denied" role="alert"><ShieldX size={18}/><span>Access denied: {error.message}</span></div>
    : <div className="error" role="alert">{error.message}</div>;
  if (loading && !data) return <div className="state" role="status"><Loader2 size={16} className="spin"/>Loading…</div>;
  if (!data) return empty ? <p className="empty-text">{empty}</p> : null;
  return <>{children(data)}</>;
}

export function Tag({ tone = 'neutral', children }: { tone?: 'neutral' | 'ok' | 'warn' | 'critical' | 'info'; children: ReactNode }) {
  return <span className={`tag tag-${tone}`}>{children}</span>;
}

export function SnapshotNote({ snapshot, completeness }: { snapshot?: SnapshotInfo; completeness?: string }) {
  if (!snapshot) return null;
  return <div className="snapshot-note"><Info size={14}/><span>Effective {fmt(snapshot.effective_at)} · known at {fmt(snapshot.known_at)} · graph {snapshot.graph_version}{completeness ? ` · ${completeness}` : ''}</span></div>;
}

export function Warning({ children }: { children: ReactNode }) {
  return <div className="warning" role="note"><AlertTriangle size={16}/><span>{children}</span></div>;
}

export function KV({ rows }: { rows: [string, unknown][] }) {
  return <dl className="kv">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{typeof v === 'object' && v !== null && !Array.isArray(v) ? fmt(v) : Array.isArray(v) ? v.map(x => fmt(x)).join(', ') || '—' : fmt(v)}</dd></div>)}</dl>;
}

