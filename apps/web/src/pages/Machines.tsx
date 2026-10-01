import { useState } from 'react';
import { KeyRound, UserPlus } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { KV, Panel, SnapshotNote, State, Tag, Warning } from '../ui';
import { severityTone } from './Radar';

export type Machine = { identity: TwinNode; owners: TwinNode[]; credentials: (TwinNode & { relationship_evidence: string })[]; dependents: TwinNode[]; direct_access: TwinNode[]; entitlements: number; privileged: string[]; tools: TwinNode[]; last_observed_use: string | null; findings: { key: string; rule: string; severity: string; title: string }[] };

export function useProposal(ctx: Ctx) {
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const propose = async (body: Record<string, unknown>) => { setBusy(true); setError(''); try {
    const r = await api<Envelope<{ id: string }>>(`${ctx.base}/change-requests`, 'POST', { ...body, idempotency_key: crypto.randomUUID() }, ctx.session.csrf_token);
    ctx.navigate('Change requests', { change: r.data.id });
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return { propose, error, busy };
}

export function MachineCard({ ctx, m, people, extra }: { ctx: Ctx; m: Machine; people: TwinNode[]; extra?: React.ReactNode }) {
  const [owner, setOwner] = useState(''); const { propose, error, busy } = useProposal(ctx);
  return <details className="finding"><summary><h3 style={{ display: 'inline-flex' }}>{m.identity.name}<Tag>{fmt(m.identity.attributes.machine_kind || m.identity.subtype)}</Tag>{m.owners.length === 0 && <Tag tone="warn">No owner</Tag>}{m.findings.map(f => <Tag key={f.key} tone={severityTone(f.severity)}>{label(f.rule)}</Tag>)}</h3></summary>
    <p>{fmt(m.identity.attributes.purpose)}</p>
    {extra}
    <KV rows={[['Owner', m.owners.map(o => o.name).join(', ') || 'None recorded'], ['Effective entitlements', m.entitlements], ['Privileged', m.privileged.join(', ') || 'None'], ['Direct access', m.direct_access.map(d => d.name).join(', ') || '—'], ['Depended on by', m.dependents.map(d => d.name).join(', ') || 'None modelled'], ['Last observed use', fmt(m.last_observed_use)]]}/>
    {m.credentials.length > 0 && <div className="table-scroll"><table><thead><tr><th>Credential (metadata only)</th><th>Type</th><th>Rotated</th><th>Expires</th><th></th></tr></thead><tbody>{m.credentials.map(c => <tr key={c.id}><td className="mono">{c.external_id}</td><td>{label(c.subtype)}</td><td>{fmt(c.attributes.rotated_at)}</td><td>{fmt(c.attributes.expires_at)}</td><td>{ctx.can('change:propose') && c.subtype !== 'federated_credential' && <button className="secondary" disabled={busy} onClick={() => propose({ kind: 'rotate_credential', credential: c.external_id, justification: `Rotate ${c.external_id} (metadata-only sandbox rotation)` })}><KeyRound size={14}/>Propose rotation</button>}</td></tr>)}</tbody></table></div>}
    {m.findings.length > 0 && <ul>{m.findings.map(f => <li key={f.key}>{f.title}</li>)}</ul>}
    {m.owners.length === 0 && ctx.can('change:propose') && <div className="button-row"><label className="inline">Owner<select aria-label={`Owner for ${m.identity.name}`} value={owner} onChange={e => setOwner(e.target.value)}><option value="">Choose a person</option>{people.filter(p => ['employee', 'admin'].includes(p.subtype) && p.status === 'active').map(p => <option key={p.id} value={p.external_id}>{p.name}</option>)}</select></label>
      <button className="secondary" disabled={busy || !owner} onClick={() => propose({ kind: 'add_relationship', type: 'USER_OWNS_SERVICE_ACCOUNT', src: owner, dst: m.identity.external_id, justification: `Assign accountable owner for ${m.identity.name}` })}><UserPlus size={14}/>Propose owner</button><small>Ownership is accountability only; it never grants access.</small></div>}
    {error && <p className="error" role="alert">{error}</p>}</details>;
}

export function Machines(ctx: Ctx) {
  const data = useResource<Envelope<Machine[]>>(`${ctx.base}/machines?subtype=machine`);
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  return <><Warning>The platform stores credential metadata only (type, rotation, expiry). Secret values are stripped at ingestion and are never displayed or exported.</Warning>
    <State {...data}>{d => <><SnapshotNote snapshot={d.snapshot}/><Panel title="Service accounts and workloads" meta={`${d.data.length}`}>{d.data.map(m => <MachineCard key={m.identity.id} ctx={ctx} m={m} people={people.data?.data || []}/>)}</Panel></>}</State></>;
}
