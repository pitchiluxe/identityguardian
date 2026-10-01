import { useEffect, useState } from 'react';
import { ArrowLeft, Check, FlaskConical } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinEdge, TwinNode } from '../api';
import { Panel, State, Tag, Warning } from '../ui';
import { Lineage } from './Access';
import type { Path } from './Access';

type SimResult = { operations: { op: string; relationship: TwinEdge; src: TwinNode; dst: TwinNode }[]; affected_identities: { identity: TwinNode; lost: { entitlement: string; decision: string; privileged: boolean }[]; retained_with_residual_routes: { entitlement: string; decision: string; removed_routes: number; residual_paths: Path[] }[]; gained: { entitlement: string; privileged: boolean }[] }[];
  possible_lockouts: { resource: TwinNode; message: string; before: number }[]; dependencies: { resource: TwinNode; depends_on: TwinNode; affected_identities: string[]; note?: string }[];
  findings: { resolved: { key: string; title: string; severity: string }[]; introduced: { key: string; title: string; severity: string }[]; statement: string }; unknowns: string[]; base: { graph_version: string; effective_at: string }; mutated_base: boolean };
export type Simulation = { id: string; digest: string; expires_at: string; base_graph_version: string; policy_version: string; source_versions: Record<string, string>; result: SimResult; created_at: string };
export type Change = { id: string; kind: string; status: string; version: number; justification: string; origin: string; origin_ref: string | null; requester_id: string; requester_name?: string; created_at: string; updated_at: string; digest: string | null; simulation_id: string | null; parameters: Record<string, unknown>;
  target: { relationship_id?: string; external_id?: string; type: string; src: TwinNode; dst: TwinNode; attributes?: Record<string, unknown> } };

export const STEPS = ['DRAFT', 'SIMULATED', 'IN_REVIEW', 'APPROVED', 'QUEUED', 'EXECUTING', 'SUCCEEDED'];
export const statusTone = (s: string) => s === 'SUCCEEDED' ? 'ok' : ['FAILED', 'REJECTED', 'PARTIAL', 'RECONCILIATION_REQUIRED'].includes(s) ? 'critical' : ['STALE', 'EXPIRED', 'CANCELLED'].includes(s) ? 'warn' : 'info';

export function SimulationView({ sim }: { sim: Simulation }) {
  const r = sim.result;
  return <>
    <div className="diff-grid"><div><small>Digest (binds exact operation, target versions, graph {sim.base_graph_version}, {sim.policy_version}, expiry)</small><p className="mono">{sim.digest}</p></div><div><small>Approval window</small><p>Expires {fmt(sim.expires_at)}</p></div><div><small>Base snapshot</small><p>{r.mutated_base ? 'MUTATED' : 'Unchanged (immutable overlay)'}</p></div></div>
    {r.possible_lockouts.length > 0 && <Warning><span><strong>Possible lockout:</strong> {r.possible_lockouts.map(l => `${l.resource.name} — ${l.message}`).join(' ')}</span></Warning>}
    <div className="pad"><h3>Affected identities ({r.affected_identities.length})</h3>{r.affected_identities.length === 0 && <p>No identity's effective access changes.</p>}
      {r.affected_identities.map(i => <div className="finding" key={i.identity.id}><h3>{i.identity.name}</h3>
        {i.lost.length > 0 && <><small className="block"><strong>Loses</strong></small><ul>{i.lost.map(l => <li key={l.entitlement}>{l.entitlement} {l.privileged && <Tag tone="warn">privileged</Tag>}</li>)}</ul></>}
        {i.retained_with_residual_routes.map(rr => <div key={rr.entitlement}><small className="block"><strong>Retains {rr.entitlement}</strong> via {rr.residual_paths.length} residual route(s); {rr.removed_routes} route(s) removed</small>{rr.residual_paths.map((p, j) => <Lineage key={j} path={p}/>)}</div>)}
        {i.gained.length > 0 && <><small className="block"><strong>Gains</strong></small><ul>{i.gained.map(g => <li key={g.entitlement}>{g.entitlement} {g.privileged && <Tag tone="warn">privileged</Tag>}</li>)}</ul></>}</div>)}
      <h3>Dependencies</h3>{r.dependencies.length === 0 ? <p>No modelled dependencies affected.</p> : <ul>{r.dependencies.map((d, i) => <li key={i}>{d.resource.name} depends on {d.depends_on.name} ({d.affected_identities.join(', ')}){d.note ? ` — ${d.note}` : ''}</li>)}</ul>}
      <h3>Findings</h3><p>{r.findings.statement}</p><ul>{r.findings.resolved.map(f => <li key={f.key}>Resolved: {f.title}</li>)}{r.findings.introduced.map(f => <li key={f.key}>Introduced: {f.title}</li>)}</ul>
      <h3>Unknowns</h3><ul>{r.unknowns.map(u => <li key={u}>{u}</li>)}</ul></div></>;
}

type Rel = TwinEdge & { other: TwinNode; direction: string };
export function WhatIf(ctx: Ctx) {
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  const [who, setWho] = useState(ctx.params.node || ''); const [rel, setRel] = useState(''); const [mode, setMode] = useState('remove'); const [group, setGroup] = useState('');
  const profile = useResource<Envelope<{ relationships: Rel[] }>>(who ? `${ctx.base}/nodes/${encodeURIComponent(who)}` : null);
  const groups = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?kind=group&limit=100`);
  const [sim, setSim] = useState<Simulation | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const removable = (profile.data?.data.relationships || []).filter(r => r.direction === 'out' && ['USER_MEMBER_OF_GROUP', 'USER_HAS_ROLE'].includes(r.type));
  const run = async () => { setBusy(true); setError(''); setSim(null); try {
    const op = mode === 'remove' ? { op: 'remove_relationship', relationship: rel } : { op: 'add_relationship', type: 'USER_MEMBER_OF_GROUP', src: who, dst: group };
    setSim((await api<Envelope<Simulation>>(`${ctx.base}/simulations`, 'POST', { operations: [op] }, ctx.session.csrf_token)).data);
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const propose = async () => { setBusy(true); setError(''); try {
    const body = mode === 'remove' ? { kind: 'remove_relationship', relationship: rel } : { kind: 'add_relationship', type: 'USER_MEMBER_OF_GROUP', src: who, dst: group };
    const r = await api<Envelope<Change>>(`${ctx.base}/change-requests`, 'POST', { ...body, justification: 'Proposed from what-if simulation', idempotency_key: crypto.randomUUID() }, ctx.session.csrf_token);
    ctx.navigate('Change requests', { change: r.data.id });
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><Panel title="Build a what-if" meta="Simulation only — nothing is changed">
    <div className="pad"><div className="form-grid"><label>Identity<select aria-label="Simulation identity" value={who} onChange={e => { setWho(e.target.value); setRel(''); setSim(null); }}><option value="">Choose an identity</option>{(people.data?.data || []).map(p => <option key={p.id} value={p.external_id}>{p.name}</option>)}</select></label>
      <label>Change<select value={mode} onChange={e => { setMode(e.target.value); setSim(null); }}><option value="remove">Remove an existing grant</option><option value="add">Add a group membership</option></select></label></div>
      {mode === 'remove' ? <label>Grant to remove<select aria-label="Grant to remove" value={rel} onChange={e => setRel(e.target.value)}><option value="">Choose a grant</option>{removable.map(r => <option key={r.relationship_id} value={r.relationship_id}>{label(r.type)} → {r.other.name}{r.attributes.ticket ? ` (${r.attributes.ticket})` : ''}</option>)}</select></label>
        : <label>Group to add<select value={group} onChange={e => setGroup(e.target.value)}><option value="">Choose a group</option>{(groups.data?.data || []).map(g => <option key={g.id} value={g.external_id}>{g.name}</option>)}</select></label>}
      <div className="button-row"><button className="primary" disabled={busy || !who || (mode === 'remove' ? !rel : !group) || !ctx.can('change:simulate')} onClick={run}><FlaskConical size={15}/>Run simulation</button>
        {sim && ctx.can('change:propose') && <button className="secondary" disabled={busy} onClick={propose}>Create change proposal</button>}
        {!ctx.can('change:simulate') && <small>Your role cannot run simulations.</small>}</div>
      {error && <p className="error" role="alert">{error}</p>}</div></Panel>
    {sim && <Panel title="Simulation result" meta={`Base graph ${sim.base_graph_version}`}><SimulationView sim={sim}/></Panel>}</>;
}

export function ChangeRequests(ctx: Ctx) {
  const list = useResource<Envelope<Change[]>>(`${ctx.base}/change-requests`);
  if (ctx.params.change) return <ChangeDetail ctx={ctx} id={ctx.params.change}/>;
  return <State {...list}>{d => <Panel title="Change requests" meta="Newest first">{d.data.length === 0 ? <p className="empty-text">No change requests.</p> : <div className="table-scroll"><table><thead><tr><th>Request</th><th>Origin</th><th>Status</th><th>Requester</th><th>Updated</th></tr></thead><tbody>
    {d.data.map(c => <tr key={c.id}><td><button className="link" onClick={() => ctx.navigate('Change requests', { change: c.id })}>{label(c.kind)}: {c.target.src.name} → {c.target.dst.name}</button><small className="mono block">{c.id.slice(0, 8)}</small></td><td>{c.origin}</td><td><Tag tone={statusTone(c.status)}>{c.status}</Tag></td><td>{c.requester_name}</td><td>{fmt(c.updated_at)}</td></tr>)}
  </tbody></table></div>}</Panel>}</State>;
}

type Detail = { change: Change; simulation: Simulation | null; history: { action: string; created_at: string; justification: string; after_state: Record<string, unknown> }[] };
export function ChangeDetail({ ctx, id }: { ctx: Ctx; id: string }) {
  const detail = useResource<Envelope<Detail>>(`${ctx.base}/change-requests/${id}`);
  const pending = ['QUEUED', 'EXECUTING', 'RECONCILIATION_REQUIRED'].includes(detail.data?.data.change.status || '');
  useEffect(() => { if (!pending) return; const timer = setInterval(detail.reload, 2000); return () => clearInterval(timer); }, [pending, detail.reload]);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); detail.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><button className="secondary back" onClick={() => ctx.navigate('Change requests')}><ArrowLeft size={15}/>All change requests</button>
    <State {...detail}>{d => { const c = d.data.change; const current = STEPS.indexOf(c.status);
      return <><Panel title={`${label(c.kind)}: ${c.target.src.name} → ${c.target.dst.name}`} meta={<Tag tone={statusTone(c.status)}>{c.status}</Tag>}>
        <div className="steps">{STEPS.map((s, i) => <span key={s} className={i < current ? 'done' : i === current ? 'current' : ''}>{s}</span>)}{current < 0 && <span className="current">{c.status}</span>}</div>
        <div className="pad"><p>{c.justification}</p><small className="block mono" data-testid="change-id">Request {c.id}</small><small className="block">Exact target: {label(c.target.type)} · {c.target.external_id || 'new relationship'} · environment {ctx.envKind} · origin {c.origin} · version {c.version}</small>
          <div className="button-row">{ctx.can('change:simulate') && ['DRAFT', 'SIMULATED', 'STALE', 'IN_REVIEW'].includes(c.status) && <button className="secondary" disabled={busy} onClick={() => act(async () => { await api(`${ctx.base}/simulations`, 'POST', { change_request_id: c.id, expected_version: c.version }, ctx.session.csrf_token); return 'Simulation recorded and bound to this request.'; })}><FlaskConical size={15}/>{c.simulation_id ? 'Re-simulate' : 'Simulate'}</button>}
            <ChangeActions ctx={ctx} change={c} busy={busy} act={act}/></div>
          {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}</div></Panel>
        {d.data.simulation && <Panel title="Bound simulation" meta={`Created ${fmt(d.data.simulation.created_at)}`}><SimulationView sim={d.data.simulation}/></Panel>}
        <Panel title="Decision trail" meta={`${d.data.history.length} audit events`}>{d.data.history.map((h, i) => <div className="history-row" key={i}><strong>{h.action}</strong><small>{fmt(h.created_at)} · {h.justification} {h.after_state.status ? `→ ${String(h.after_state.status)}` : ''}</small></div>)}</Panel></>; }}</State></>;
}

export function ChangeActions({ ctx, change, busy, act }: { ctx: Ctx; change: Change; busy: boolean; act: (fn: () => Promise<string>) => void }) {
  const [why, setWhy] = useState('');
  const jit = change.kind === 'jit_grant';
  const canApprove = ctx.can(jit ? 'jit:approve' : 'change:approve') && change.requester_id !== ctx.session.user.id;
  const canExecute = ctx.can(jit ? 'jit:execute' : 'change:execute');
  const mfaAge = Date.now() / 1000 - ctx.session.auth_time;
  const mfa = (ctx.session.amr.includes('mfa') || (ctx.session.amr.includes('pwd') && ctx.session.amr.includes('otp'))) && mfaAge <= 300;
  const csrf = ctx.session.csrf_token; const base = `${ctx.base}/change-requests/${change.id}`;
  return <>
    {change.status === 'SIMULATED' && ctx.can('change:propose') && <button className="primary" disabled={busy} onClick={() => act(async () => { await api(`${base}/submit`, 'POST', { expected_version: change.version }, csrf); return 'Submitted for independent approval.'; })}>Submit for approval</button>}
    {change.status === 'IN_REVIEW' && canApprove && <div className="approval-box"><p><strong>Approve this exact proposal</strong> · digest <code className="mono">{change.digest}</code></p>
      {!mfa && <Warning>Approval requires MFA verified within the last 5 minutes. Sign out and sign in again with your one-time code.</Warning>}
      <label>Approval justification<textarea minLength={8} value={why} onChange={e => setWhy(e.target.value)} placeholder="Reference the simulation evidence you reviewed."/></label>
      <div className="button-row"><button className="primary" disabled={busy || why.length < 8} onClick={() => act(async () => { await api(`${base}/decision`, 'POST', { digest: change.digest, decision: 'APPROVE', justification: why }, csrf); return 'Approved. Execution is a separate action by another operator.'; })}>Approve exact digest</button>
        <button className="secondary" disabled={busy || why.length < 8} onClick={() => act(async () => { await api(`${base}/decision`, 'POST', { digest: change.digest, decision: 'REJECT', justification: why }, csrf); return 'Rejected.'; })}>Reject</button></div></div>}
    {change.status === 'IN_REVIEW' && change.requester_id === ctx.session.user.id && <small>Awaiting an independent approver (you requested this change).</small>}
    {change.status === 'APPROVED' && canExecute && <button className="primary" disabled={busy} onClick={() => act(async () => { await api(`${base}/execute`, 'POST', { digest: change.digest }, csrf); return 'Queued for sandbox execution. Status updates when the source confirms.'; })}>Execute in {ctx.envKind} sandbox</button>}
    {['QUEUED', 'EXECUTING', 'RECONCILIATION_REQUIRED'].includes(change.status) && <small>Pending is not success: waiting for the worker to confirm the source result (updates automatically).</small>}
    {['DRAFT', 'SIMULATED', 'STALE'].includes(change.status) && change.requester_id === ctx.session.user.id && <button className="secondary" disabled={busy} onClick={() => act(async () => { await api(`${base}/cancel`, 'POST', { expected_version: change.version }, csrf); return 'Cancelled.'; })}>Cancel request</button>}
  </>;
}
