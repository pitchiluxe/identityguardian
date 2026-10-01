import { useState } from 'react';
import { History, ShieldCheck } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { Panel, State, Tag, Warning } from '../ui';
import { decisionTone } from './Access';

type View = { status: string; reason?: string; entitlements: { entitlement: string; decision: string; routes: number }[] };
type Reconstruction = { identity: { name: string }; effective_at: string; known_at: string; timezone: string; as_known_then: View; as_known_now: View;
  differences: { entitlement: string; kind: string; explanation: string }[]; coverage: { notes: string[]; earliest_effective_evidence: string | null; first_observation: string | null; syncs_before_known_at: { finished_at: string; status: string; coverage: string }[] }; graph_versions: { then: string; now: string } };
type Snap = { id: string; effective_at: string; known_at: string; checksum: string; node_count: number; edge_count: number };
const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const iso = (local: string) => local ? new Date(local).toISOString() : '';

export function TimeMachine(ctx: Ctx) {
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  const [who, setWho] = useState(ctx.params.node || 'idn-erick'); const [effective, setEffective] = useState('2026-05-01T12:00'); const [known, setKnown] = useState('');
  const q = new URLSearchParams({ effective_at: iso(effective), ...(known ? { known_at: iso(known) } : {}) });
  const result = useResource<Envelope<Reconstruction>>(who && effective ? `${ctx.base}/history/identities/${encodeURIComponent(who)}?${q}` : null);
  return <><div className="toolbar"><label className="inline">Identity<select aria-label="History identity" value={who} onChange={e => setWho(e.target.value)}>{(people.data?.data || []).map(p => <option key={p.id} value={p.external_id}>{p.name}</option>)}</select></label>
    <label className="inline">Effective at<input type="datetime-local" aria-label="History effective at" value={effective} onChange={e => setEffective(e.target.value)}/></label>
    <label className="inline">Known at<input type="datetime-local" aria-label="History known at" value={known} onChange={e => setKnown(e.target.value)}/></label>
    <small>Times entered in {zone}; stored and compared in UTC. Empty “known at” means current knowledge.</small></div>
    <State {...result}>{d => { const r = d.data; return <>
      <Panel title={`${r.identity.name} at ${fmt(r.effective_at)}`} meta={`Knowledge as of ${fmt(r.known_at)} · ${r.timezone}`}>
        {r.coverage.notes.length > 0 && <div className="pad"><Warning><span>{r.coverage.notes.join(' ')}</span></Warning></div>}
        <div className="diff-grid"><HistoryView title="As known then" view={r.as_known_then} version={r.graph_versions.then}/><HistoryView title="As known now (same effective time)" view={r.as_known_now} version={r.graph_versions.now}/></div>
        {r.differences.length > 0 && <div className="pad"><h3>Differences</h3><ul>{r.differences.map(x => <li key={x.entitlement + x.kind}><Tag tone={x.kind === 'LEARNED_LATER' ? 'warn' : 'info'}>{x.kind}</Tag> {x.entitlement} — {x.explanation}</li>)}</ul></div>}
        <div className="pad"><small>Earliest source evidence {fmt(r.coverage.earliest_effective_evidence)} · first observation {fmt(r.coverage.first_observation)} · {r.coverage.syncs_before_known_at.length} sync(s) before the knowledge time</small></div></Panel>
      <Snapshots ctx={ctx} effective={r.effective_at} known={known ? r.known_at : undefined}/></>; }}</State></>;
}

function HistoryView({ title, view, version }: { title: string; view: View; version: string }) {
  return <div><small>{title} · graph {version}</small>{view.status === 'UNKNOWN' ? <p><Tag tone="warn">UNKNOWN</Tag> {view.reason}</p> : view.entitlements.length === 0 ? <p>No effective entitlements.</p> : <ul>{view.entitlements.map(e => <li key={e.entitlement}>{e.entitlement} <Tag tone={decisionTone(e.decision)}>{e.decision}</Tag> <small>{e.routes} route(s)</small></li>)}</ul>}</div>;
}

function Snapshots({ ctx, effective, known }: { ctx: Ctx; effective: string; known?: string }) {
  const list = useResource<Envelope<Snap[]>>(`${ctx.base}/history/snapshots`);
  const [verdict, setVerdict] = useState<Record<string, string>>({}); const [error, setError] = useState('');
  const create = async () => { setError(''); try { await api(`${ctx.base}/history/snapshots`, 'POST', { effective_at: effective, ...(known ? { known_at: known } : {}) }, ctx.session.csrf_token); list.reload(); } catch (e) { setError((e as Error).message); } };
  const verify = async (id: string) => { try { const r = await api<Envelope<{ result: string }>>(`${ctx.base}/history/snapshots/${id}/verify`); setVerdict({ ...verdict, [id]: r.data.result }); } catch (e) { setError((e as Error).message); } };
  return <Panel title="Checksummed snapshots" meta="Replay verification" actions={<button className="secondary" onClick={create}><History size={14}/>Snapshot this view</button>}>
    {error && <p className="error" role="alert">{error}</p>}
    <State {...list}>{d => d.data.length === 0 ? <p className="empty-text">No snapshots yet.</p> : <div className="table-scroll"><table><thead><tr><th>Effective</th><th>Known</th><th>Size</th><th>Checksum</th><th>Verify</th></tr></thead><tbody>{d.data.map(s => <tr key={s.id}><td>{fmt(s.effective_at)}</td><td>{fmt(s.known_at)}</td><td>{s.node_count} nodes · {s.edge_count} edges</td><td className="mono">{s.checksum.slice(0, 16)}</td><td>{verdict[s.id] ? <Tag tone={verdict[s.id] === 'MATCH' ? 'ok' : 'critical'}>{verdict[s.id]}</Tag> : <button className="link" onClick={() => verify(s.id)}><ShieldCheck size={13}/> Replay</button>}</td></tr>)}</tbody></table></div>}</State></Panel>;
}
