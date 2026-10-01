import { useState } from 'react';
import { fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinEdge, TwinNode } from '../api';
import { Panel, SnapshotNote, State, Tag } from '../ui';
import { Lineage, decisionTone } from './Access';
import type { Path } from './Access';

export type Finding = { key: string; rule: string; severity: string; basis: string; rules_version: string; identity: TwinNode; title: string; summary: string; recommendation: string; evidence_ids: string[];
  grant?: TwinEdge; event?: { kind: string; effective_at: string; details: Record<string, string>; evidence_id: string }; peers?: { sample_size: number; holding: number };
  reaches: { target: string; target_id: string; decision: string; privileged: boolean; paths: Path[] }[]; usage: { target: string; state: string; text: string }[] };

export const severityTone = (s: string) => s === 'critical' ? 'critical' : s === 'high' ? 'warn' : s === 'medium' ? 'info' : 'neutral';

export function FindingCard({ f, ctx, actions }: { f: Finding; ctx: Ctx; actions?: React.ReactNode }) {
  return <details className="finding"><summary><h3 style={{ display: 'inline-flex' }}><Tag tone={severityTone(f.severity)}>{f.severity.toUpperCase()}</Tag>{f.title}<Tag>{label(f.rule)}</Tag></h3></summary>
    <p>{f.summary}</p>
    {f.peers && <small className="block">Peer comparison: {f.peers.holding} of {f.peers.sample_size} peers in the current department hold this grant (sample size {f.peers.sample_size}).</small>}
    {f.event && <small className="block">Evidence event: {label(f.event.kind)} effective {fmt(f.event.effective_at)} · evidence {f.event.evidence_id.slice(0, 8)}</small>}
    <ul>{f.usage.map((u, i) => <li key={i}><strong>{u.target}:</strong> {u.text}</li>)}</ul>
    {f.reaches.map(r => <div key={r.target_id}><small className="block"><strong>Reaches {r.target}</strong> <Tag tone={decisionTone(r.decision)}>{r.decision}</Tag>{r.privileged && <Tag tone="warn">privileged</Tag>}</small>{r.paths.slice(0, 2).map((p, i) => <Lineage key={i} path={p} start={f.identity.name}/>)}</div>)}
    <small className="block">Recommendation ({f.basis}, {f.rules_version}): <strong>{f.recommendation}</strong>. A recommendation never changes access; changes require simulation and independent approval.</small>
    <div className="button-row">{ctx.can('identity:read') && <button className="secondary" onClick={() => ctx.navigate('Identities', { node: f.identity.external_id })}>Open profile</button>}{actions}</div>
    <small className="mono block">Finding {f.key} · evidence {f.evidence_ids.map(e => e.slice(0, 8)).join(' ')}</small></details>;
}

export function Radar(ctx: Ctx) {
  const [rule, setRule] = useState('');
  const result = useResource<Envelope<Finding[]>>(`${ctx.base}/findings${rule ? `?rule=${rule}` : ''}`);
  const counts = (result.data?.counts || {}) as Record<string, number>;
  return <><div className="toolbar"><label className="inline">Rule<select value={rule} onChange={e => setRule(e.target.value)}><option value="">All rules</option>{['PRIOR_ROLE_RETAINED', 'TERMINATED_WITH_ACCESS', 'DORMANT_PRIVILEGED', 'UNUSED_PRIVILEGED_ENTITLEMENT'].map(r => <option key={r} value={r}>{label(r)}{counts[r] !== undefined ? ` (${counts[r]})` : ''}</option>)}</select></label>
    <small>Deterministic rule-based findings. Each cites evidence and states telemetry coverage.</small></div>
    <State {...result}>{d => <><SnapshotNote snapshot={d.snapshot}/><Panel title="Findings" meta={`${d.data.length} · ${String(d.rules_version)}`}>{d.data.length === 0 ? <p className="empty-text">No findings for the selected rule at this time.</p> : d.data.map(f => <FindingCard key={f.key} f={f} ctx={ctx}/>)}</Panel></>}</State></>;
}

type Timeline = { identity: TwinNode; events: { at: string; kind: string; text: string; evidence_id: string | null }[] };
export function TimelinePanel({ ctx, node }: { ctx: Ctx; node: string }) {
  const t = useResource<Envelope<Timeline>>(`${ctx.base}/identities/${encodeURIComponent(node)}/timeline`);
  return <State {...t}>{d => <Panel title="Timeline" meta={`${d.data.events.length} events · effective time`}>{d.data.events.map((e, i) => <div className="history-row" key={i}><strong><Tag tone={e.kind.startsWith('employment') ? 'info' : e.kind === 'grant.end' ? 'warn' : 'neutral'}>{e.kind}</Tag> {e.text}</strong><small>{fmt(e.at)}{e.evidence_id ? ` · evidence ${e.evidence_id.slice(0, 8)}` : ''}</small></div>)}</Panel>}</State>;
}
