import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinEdge, TwinNode } from '../api';
import { Panel, SnapshotNote, State, Tag, Warning } from '../ui';

export type Hop = { edge: TwinEdge; to: TwinNode };
export type Path = { status: string; hops: Hop[]; conditions: { type: string; supported: boolean }[]; evidence_ids: string[]; origin: string; denied_by: TwinEdge | null };
type Usage = { last_observed_use: string | null; observed_events: number; coverage: { covered_from: string; covered_to: string; completeness: string }[] } | null;
type Entry = { resource: TwinNode | null; permission: TwinNode | null; action: string; decision: string; paths: Path[]; usage: Usage };
type AccessResult = { identity: TwinNode; entries: Entry[]; denies: TwinEdge[]; complete: boolean; truncation_reason: string | null };
type Principals = { target: TwinNode; principals: { identity: TwinNode; decision: string; paths: Path[] }[]; complete: boolean; truncation_reason: string | null };

export const decisionTone = (d: string) => d === 'ALLOW' ? 'ok' : d === 'DENY' ? 'critical' : 'warn';

export function Lineage({ path, start }: { path: Path; start?: string }) {
  return <div className="chain" aria-label="Access lineage">{start && <span className="hop"><strong>{start}</strong><small>identity</small></span>}
    {path.hops.map(h => <span key={h.edge.id} style={{ display: 'contents' }}><span className="via"><ChevronRight size={14}/>{label(h.edge.type)}{h.edge.attributes.ticket ? <em>{String(h.edge.attributes.ticket)}</em> : null}</span>
      <span className="hop"><strong>{h.to.name}</strong><small>{h.to.kind}{h.edge.attributes.approver ? ` · approved by ${String(h.edge.attributes.approver).replace('idn-', '')}` : ''}</small><small>since {fmt(h.edge.valid_from).slice(0, 10)}{h.edge.attributes.expires_at ? ` · expires ${fmt(h.edge.attributes.expires_at).slice(0, 10)}` : ''}</small></span></span>)}
    <Tag tone={decisionTone(path.status)}>{path.status}</Tag>
    {path.conditions.length > 0 && <small className="block">Conditions: {path.conditions.map(c => `${c.type}${c.supported ? '' : ' (unsupported → UNKNOWN)'}`).join(', ')}</small>}
    {path.denied_by && <small className="block">Explicit deny: {fmt(path.denied_by.attributes.justification)}</small>}</div>;
}

function UsageNote({ usage }: { usage: Usage }) {
  if (!usage) return <small className="muted">No usage telemetry applies to this entitlement.</small>;
  if (usage.coverage.length === 0) return <small>Usage unknown: no telemetry coverage for this target.</small>;
  const windows = usage.coverage.map(c => `${c.covered_from.slice(0, 10)}→${c.covered_to.slice(0, 10)} (${c.completeness})`).join(', ');
  return <small>{usage.observed_events > 0 ? `Last observed use ${fmt(usage.last_observed_use)} (${usage.observed_events} events)` : 'No observed use during coverage'} · coverage {windows}. Absence of observed use is not proof of never-used access.</small>;
}

export function Access(ctx: Ctx) {
  const [who, setWho] = useState(ctx.params.node || ''); const [draft, setDraft] = useState(ctx.params.node || '');
  const [target, setTarget] = useState(ctx.params.target || '');
  const [at, setAt] = useState('');
  const atParam = at ? `?effective_at=${encodeURIComponent(new Date(at).toISOString())}` : '';
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  const result = useResource<Envelope<AccessResult>>(who ? `${ctx.base}/identities/${encodeURIComponent(who)}/access${atParam}` : null);
  const reverse = useResource<Envelope<Principals>>(target ? `${ctx.base}/resources/${encodeURIComponent(target)}/principals${atParam}` : null);
  return <>
    <div className="toolbar"><label className="inline">Identity<select aria-label="Identity" value={draft} onChange={e => { setDraft(e.target.value); setWho(e.target.value); setTarget(''); }}><option value="">Choose an identity</option>{(people.data?.data || []).map(p => <option key={p.id} value={p.external_id}>{p.name} ({p.subtype})</option>)}</select></label>
      <label className="inline">Effective at (your local time)<input type="datetime-local" aria-label="Effective at" value={at} onChange={e => setAt(e.target.value)}/></label>
      {at && <button className="secondary" onClick={() => setAt('')}>Now</button>}</div>
    {target && <State {...reverse}>{d => <Panel title={`Who can access ${d.data.target.name}`} meta={`${d.data.principals.length} identities`} actions={<button className="secondary" onClick={() => setTarget('')}>Close</button>}>
      <SnapshotNote snapshot={d.snapshot} completeness={d.completeness}/>{!d.data.complete && <Warning>Partial: {d.data.truncation_reason}. Other principals may exist.</Warning>}
      {d.data.principals.map(p => <div className="finding" key={p.identity.id}><h3><button className="link" onClick={() => { setWho(p.identity.external_id); setDraft(p.identity.external_id); setTarget(''); }}>{p.identity.name}</button><Tag tone={decisionTone(p.decision)}>{p.decision}</Tag><small>{p.paths.length} route{p.paths.length > 1 ? 's' : ''}</small></h3>{p.paths.map((path, i) => <Lineage key={i} path={path}/>)}</div>)}</Panel>}</State>}
    {!who ? <p className="empty-text">Choose an identity to calculate effective access with lineage and evidence.</p> :
      <State {...result}>{d => <>
        <SnapshotNote snapshot={d.snapshot} completeness={d.completeness}/>
        {!d.data.complete && <Warning>Traversal bound reached ({d.data.truncation_reason}). Results are partial and do not prove absence of further access.</Warning>}
        <Panel title={`Effective access · ${d.data.identity.name}`} meta={`${d.data.entries.length} entitlements · depth ≤ 8`}>
          {d.data.entries.length === 0 && <p className="empty-text">No grant routes found at this time.</p>}
          {d.data.entries.map((e, i) => <details className="finding" key={i} open={i < 3}><summary><h3 style={{ display: 'inline-flex' }}>{(e.resource || e.permission)!.name} · {e.permission ? e.permission.name : label(e.action)}<Tag tone={decisionTone(e.decision)}>{e.decision}</Tag><small>{e.paths.length} route{e.paths.length > 1 ? 's' : ''}</small></h3></summary>
            <UsageNote usage={e.usage}/>{e.resource && ctx.can('access:read') && <button className="link block" onClick={() => setTarget(e.resource!.external_id)}>Who else can access {e.resource.name}?</button>}
            {e.paths.map((p, j) => <Lineage key={j} path={p} start={d.data.identity.name}/>)}<small className="mono block">Evidence: {[...new Set(e.paths.flatMap(p => p.evidence_ids))].map(x => x.slice(0, 8)).join(' ')}</small></details>)}
        </Panel></>}</State>}</>;
}
