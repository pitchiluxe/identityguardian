import { useState } from 'react';
import { ChevronRight, ShieldAlert } from 'lucide-react';
import { label, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { Panel, SnapshotNote, State, Tag, Warning } from '../ui';

type Step = { kind: string; from_: TwinNode; to: TwinNode; status: string; factors: { type: string; effect?: string; supported?: boolean }[]; evidence_ids: string[]; edges: { type: string; attributes: Record<string, unknown> }[] };
type AttackPath = { key: string; source: TwinNode; destination: TwinNode; status: string; sensitivity: string; steps: Step[]; defensive_controls: string[]; statement: string; evidence_ids: string[] };
type Result = { paths: AttackPath[]; complete: boolean; truncation_reason: string | null; rules_version: string; max_steps: number };
const tone = (s: string) => s === 'POTENTIAL' ? 'critical' : s === 'CONDITIONAL' ? 'warn' : 'neutral';

export function AttackPaths(ctx: Ctx) {
  const [source, setSource] = useState(ctx.params.node || ''); const [steps, setSteps] = useState(2);
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  const result = useResource<Envelope<Result>>(`${ctx.base}/attack-paths?max_steps=${steps}${source ? `&source=${encodeURIComponent(source)}` : ''}`);
  return <><Warning>Defensive analysis only. Paths show evidenced prerequisites and controls for potential exposure; they are not exploitation instructions and do not prove compromise.</Warning>
    <div className="toolbar"><label className="inline">Starting identity<select value={source} onChange={e => setSource(e.target.value)}><option value="">All active identities</option>{(people.data?.data || []).map(p => <option key={p.id} value={p.external_id}>{p.name}</option>)}</select></label>
      <label className="inline">Max transitions<select value={steps} onChange={e => setSteps(Number(e.target.value))}>{[1, 2, 3].map(n => <option key={n}>{n}</option>)}</select></label></div>
    <State {...result}>{d => <><SnapshotNote snapshot={d.snapshot} completeness={d.completeness}/>{!d.data.complete && <Warning>Search bounded: {d.data.truncation_reason}. Unlisted paths may exist; this is not proof of absence.</Warning>}
      <Panel title="Exposure paths to sensitive resources" meta={`${d.data.paths.length} · ${d.data.rules_version}`}>{d.data.paths.length === 0 ? <p className="empty-text">No exposure paths found within the bounds.</p> : d.data.paths.map(p => <details className="finding" key={p.key}><summary><h3 style={{ display: 'inline-flex' }}><ShieldAlert size={16}/>{p.source.name} → {p.destination.name}<Tag tone={tone(p.status)}>{p.status}</Tag><Tag>{p.sensitivity}</Tag></h3></summary>
        <div className="chain"><span className="hop"><strong>{p.source.name}</strong><small>start</small></span>{p.steps.map((s, i) => <span key={i} style={{ display: 'contents' }}><span className="via"><ChevronRight size={14}/>{label(s.kind)}<em>{s.status}</em></span><span className="hop"><strong>{s.to.name}</strong><small>{s.to.kind}</small></span></span>)}</div>
        <ul>{p.steps.flatMap((s, i) => s.factors.map((f, j) => <li key={`${i}-${j}`}>{label(s.kind)} · <strong>{f.type}</strong>: {f.effect || (f.supported === false ? 'unsupported condition' : 'condition applies')}</li>))}</ul>
        <p>{p.statement}</p><h3>Defensive controls</h3><ul>{p.defensive_controls.map(c => <li key={c}>{c}</li>)}</ul>
        <small className="mono block">Evidence {p.evidence_ids.map(e => e.slice(0, 8)).join(' ')}</small></details>)}</Panel></>}</State></>;
}
