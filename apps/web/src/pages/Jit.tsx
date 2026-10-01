import { useEffect, useState } from 'react';
import { Check, Clock3 } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { Panel, State, Tag, Warning } from '../ui';
import { statusTone } from './Changes';
import type { Change } from './Changes';

type Grant = { id: string; change_request_id: string; status: string; granted_at: string; expires_at: string; revoked_at: string | null; attempts: number; last_error: string | null; overdue: boolean; target: Change['target']; justification: string };
type Jit = { grants: Grant[]; requests: Change[]; overdue: Grant[] };

export function JitAccess(ctx: Ctx) {
  const data = useResource<Envelope<Jit>>(`${ctx.base}/jit-grants`);
  const inFlight = (data.data?.data.requests || []).some(r => ['QUEUED', 'EXECUTING'].includes(r.status));
  useEffect(() => { if (!inFlight) return; const timer = setInterval(data.reload, 2000); return () => clearInterval(timer); }, [inFlight, data.reload]);
  const people = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?limit=100`);
  const groups = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?kind=group&limit=100`);
  const [who, setWho] = useState(''); const [group, setGroup] = useState(''); const [minutes, setMinutes] = useState(60); const [why, setWhy] = useState('');
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(''); setNotice(''); try {
    await api(`${ctx.base}/jit-requests`, 'POST', { identity: who, group, duration_minutes: minutes, justification: why, idempotency_key: crypto.randomUUID() }, ctx.session.csrf_token);
    setNotice('Request simulated and submitted for independent approval.'); setWhy(''); data.reload();
  } catch (err) { setError((err as Error).message); } finally { setBusy(false); } };
  return <>
    {ctx.can('jit:request') && <form className="panel proposal" onSubmit={submit}><h2>Request temporary access</h2><p>Bounded duration (15 minutes to 8 hours). The grant is created at the sandbox source with a native expiry; the worker revokes it at expiry under the original approval and never extends it.</p>
      <div className="form-grid"><label>Identity<select aria-label="JIT identity" required value={who} onChange={e => setWho(e.target.value)}><option value="">Choose an identity</option>{(people.data?.data || []).filter(p => p.subtype !== 'machine').map(p => <option key={p.id} value={p.external_id}>{p.name}</option>)}</select></label>
        <label>Group<select aria-label="JIT group" required value={group} onChange={e => setGroup(e.target.value)}><option value="">Choose a group</option>{(groups.data?.data || []).map(g => <option key={g.id} value={g.external_id}>{g.name}</option>)}</select></label>
        <label>Duration (minutes)<select value={minutes} onChange={e => setMinutes(Number(e.target.value))}>{[15, 30, 60, 120, 240, 480].map(m => <option key={m}>{m}</option>)}</select></label></div>
      <label>Justification<textarea required minLength={8} value={why} onChange={e => setWhy(e.target.value)} placeholder="Incident or ticket reference and why temporary access is needed."/></label>
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
      <button className="primary" disabled={busy}><Clock3 size={15}/>Simulate and submit</button></form>}
    <State {...data}>{d => <>
      {d.data.overdue.length > 0 && <Warning>{d.data.overdue.length} grant(s) are overdue for revocation. Revocation is unconfirmed while the source is unavailable; operators should investigate.</Warning>}
      <Panel title="Requests in progress" meta={`${d.data.requests.length}`}>{d.data.requests.length === 0 ? <p className="empty-text">No pending temporary access requests.</p> : <div className="table-scroll"><table><thead><tr><th>Request</th><th>Duration</th><th>Status</th><th>Created</th></tr></thead><tbody>
        {d.data.requests.map(r => <tr key={r.id}><td><button className="link" onClick={() => ctx.navigate('Change requests', { change: r.id })}>{r.target.src.name} → {r.target.dst.name}</button></td><td>{String(r.parameters.duration_minutes)} min</td><td><Tag tone={statusTone(r.status)}>{r.status}</Tag></td><td>{fmt(r.created_at)}</td></tr>)}</tbody></table></div>}</Panel>
      <Panel title="Temporary grants" meta={`${d.data.grants.length}`}>{d.data.grants.length === 0 ? <p className="empty-text">No temporary grants have been executed.</p> : <div className="table-scroll"><table><thead><tr><th>Grant</th><th>Window</th><th>Status</th><th>Revocation</th></tr></thead><tbody>
        {d.data.grants.map(g => <tr key={g.id}><td><button className="link" onClick={() => ctx.navigate('Change requests', { change: g.change_request_id })}>{g.target.src.name} → {g.target.dst.name}</button></td><td>{fmt(g.granted_at)} → {fmt(g.expires_at)}</td><td><Tag tone={g.status === 'ACTIVE' ? 'info' : g.status === 'EXPIRED' ? 'ok' : 'critical'}>{g.status}</Tag>{g.overdue && <Tag tone="critical">OVERDUE</Tag>}</td><td>{g.revoked_at ? `Confirmed ${fmt(g.revoked_at)}` : g.last_error ? `Pending: ${g.last_error}` : 'Scheduled at expiry'}</td></tr>)}</tbody></table></div>}</Panel></>}</State></>;
}
