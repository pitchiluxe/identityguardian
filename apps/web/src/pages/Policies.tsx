import { useState } from 'react';
import { Check, FileCheck2 } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { Panel, State, Tag, Warning } from '../ui';

type Version = { id: string; policy_id: string; version: number; status: string; definition: { name: string; purpose: string; action: string; tests: unknown[] }; proposed_by: string; proposed_by_name: string; approved_by_name: string | null;
  test_results: { name: string; expected: string; actual: string; passed: boolean }[] | null; simulation: { violations: { identity: TwinNode; target: TwinNode }[]; excepted: { identity: string; target: string }[]; statement: string } | null; approval_digest: string | null; activated_at: string | null };
const STEPS = ['DRAFT', 'TESTED', 'SIMULATED', 'APPROVED', 'ACTIVE'];
const TEMPLATE = JSON.stringify({
  schema_version: '1', name: 'No permanent Global Administrator for contractors', purpose: 'Contractors may only hold Global Administrator with an expiry.',
  scope: { identity_subtypes: ['contractor'] }, conditions: { all: [{ field: 'target.name', op: 'eq', value: 'Global Administrator' }, { field: 'grant.expires_at', op: 'missing' }] },
  action: 'flag', exceptions: [], tests: [
    { name: 'permanent contractor', expect: 'violation', input: { 'identity.subtype': 'contractor', 'target.name': 'Global Administrator' } },
    { name: 'time-bound contractor', expect: 'no_violation', input: { 'identity.subtype': 'contractor', 'target.name': 'Global Administrator', 'grant.expires_at': '2026-12-01T00:00:00+00:00' } }],
}, null, 2);

export function Policies(ctx: Ctx) {
  const list = useResource<Envelope<Version[]>>(`${ctx.base}/policies`);
  const [text, setText] = useState(TEMPLATE); const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); list.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const csrf = ctx.session.csrf_token; const base = `${ctx.base}/policies/versions`;
  return <><Warning>Policies are declarative data over allowlisted fields and operators; no code runs. FLAG reports matching grants; it never revokes. REJECT_PROPOSED blocks new proposals that would violate it.</Warning>
    {ctx.can('policy:propose') && <Panel title="Propose a policy version" meta="schema_version 1">
      <div className="pad"><label>Definition (JSON)<textarea className="code" aria-label="Policy definition" rows={16} value={text} onChange={e => setText(e.target.value)}/></label>
        <button className="primary" disabled={busy} onClick={() => act(async () => { let definition; try { definition = JSON.parse(text); } catch { throw new Error('Definition is not valid JSON'); } await api(`${ctx.base}/policies`, 'POST', { definition }, csrf); return 'Draft recorded. Run its tests next.'; })}><FileCheck2 size={15}/>Validate and save draft</button></div></Panel>}
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    <State {...list}>{d => <Panel title="Policy versions" meta={`${d.data.length}`}>{d.data.length === 0 ? <p className="empty-text">No policies yet.</p> : d.data.map(v => { const i = STEPS.indexOf(v.status); return <details className="finding" key={v.id} open={v.status !== 'SUPERSEDED'}>
      <summary><h3 style={{ display: 'inline-flex' }}>{v.definition.name} · v{v.version}<Tag tone={v.status === 'ACTIVE' ? 'ok' : v.status === 'TEST_FAILED' || v.status === 'REJECTED' ? 'critical' : 'info'}>{v.status}</Tag><Tag>{v.definition.action}</Tag></h3></summary>
      <div className="steps">{STEPS.map((s, j) => <span key={s} className={j < i ? 'done' : j === i ? 'current' : ''}>{s}</span>)}</div>
      <p>{v.definition.purpose}</p><small className="block">Proposed by {v.proposed_by_name}{v.approved_by_name ? ` · approved by ${v.approved_by_name}` : ''}{v.activated_at ? ` · active since ${fmt(v.activated_at)}` : ''}</small>
      {v.test_results && <ul>{v.test_results.map(r => <li key={r.name}><Tag tone={r.passed ? 'ok' : 'critical'}>{r.passed ? 'PASS' : 'FAIL'}</Tag> {r.name}: expected {r.expected}, got {r.actual}</li>)}</ul>}
      {v.simulation && <><p><strong>{v.simulation.violations.length}</strong> existing grant(s) match. {v.simulation.statement}</p><ul>{v.simulation.violations.map((x, k) => <li key={k}>{x.identity.name} → {x.target.name}</li>)}{v.simulation.excepted.map((x, k) => <li key={`e${k}`}>Excepted: {x.identity} → {x.target}</li>)}</ul>{v.approval_digest && <small className="mono block">Approval digest {v.approval_digest}</small>}</>}
      <div className="button-row">
        {['DRAFT', 'TEST_FAILED'].includes(v.status) && ctx.can('policy:propose') && <button className="secondary" disabled={busy} onClick={() => act(async () => { await api(`${base}/${v.id}/test`, 'POST', {}, csrf); return 'Tests executed.'; })}>Run tests</button>}
        {v.status === 'TESTED' && ctx.can('policy:propose') && <button className="secondary" disabled={busy} onClick={() => act(async () => { await api(`${base}/${v.id}/simulate`, 'POST', {}, csrf); return 'Simulated against the current twin.'; })}>Simulate scope</button>}
        {v.status === 'SIMULATED' && ctx.can('policy:approve') && v.proposed_by !== ctx.session.user.id && <button className="primary" disabled={busy} onClick={() => act(async () => { await api(`${base}/${v.id}/decision`, 'POST', { digest: v.approval_digest, decision: 'APPROVE' }, csrf); return 'Approved. Activation is a separate step.'; })}>Approve exact digest</button>}
        {v.status === 'APPROVED' && ctx.can('policy:propose') && <button className="primary" disabled={busy} onClick={() => act(async () => { await api(`${base}/${v.id}/activate`, 'POST', {}, csrf); return 'Policy version active.'; })}>Activate</button>}
      </div></details>; })}</Panel>}</State></>;
}
