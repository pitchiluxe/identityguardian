import { useEffect, useState } from 'react';
import { Check, ChevronRight, ScrollText } from 'lucide-react';
import { api } from '../api';
import type { Session } from '../api';

type Member = { user_id: string; display_name: string; roles: string[]; version: number; active: boolean };
type Change = { id: string; target_id: string; requester_id: string; previous_roles: string[]; roles: string[]; justification: string; digest: string; status: string; expires_at: string };
type Audit = { id: string; action: string; target: string; created_at: string; result: string; justification: string; correlation_id: string; before_state: object; after_state: object };
const roleNames = ['viewer', 'investigator', 'reviewer', 'approver', 'operator', 'org_admin', 'auditor', 'learner'];

export function Administration({ org, session, can }: { org: string; session: Session; can: (s: string) => boolean }) {
  const [members, setMembers] = useState<Member[]>([]); const [changes, setChanges] = useState<Change[]>([]);
  const [target, setTarget] = useState(''); const [role, setRole] = useState('viewer'); const [reason, setReason] = useState('');
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const base = `/organizations/${org}`;
  const refresh = async () => { const [m, c] = await Promise.all([api<Member[]>(base + '/members'), api<Change[]>(base + '/role-requests')]); setMembers(m); setChanges(c); };
  useEffect(() => { refresh().catch(e => setError(e.message)); }, [org]);
  const propose = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(''); setNotice(''); try {
    const member = members.find(m => m.user_id === target)!;
    await api(base + '/role-requests', 'POST', { target_id: target, roles: [role], justification: reason, expected_version: member.version, idempotency_key: crypto.randomUUID() }, session.csrf_token);
    setNotice('Proposal recorded. An independent approver must review the exact role replacement.'); setReason(''); await refresh();
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const decide = async (change: Change, action: string) => { setBusy(true); setError(''); setNotice(''); try {
    await api(base + `/role-requests/${change.id}/${action}`, 'POST', { digest: change.digest }, session.csrf_token);
    setNotice(action === 'approve' ? 'Approval recorded. Execution is a separate action.' : 'Platform roles updated and audited.'); await refresh();
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><section className="panel"><div className="section-heading"><h2>Organization members</h2><span>First 100 members</span></div><div className="table-scroll"><table><thead><tr><th>Member</th><th>Platform roles</th><th>State</th></tr></thead><tbody>{members.map(m => <tr key={m.user_id}><td>{m.display_name}{m.user_id === session.user.id && <span className="muted"> (you)</span>}</td><td>{m.roles.join(', ')}</td><td><span className="ready-tag">{m.active ? 'Active' : 'Inactive'}</span></td></tr>)}</tbody></table></div></section>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    {can('members:propose') && <form className="panel proposal" onSubmit={propose}><h2>Propose a platform role replacement</h2><p>This replaces the selected member’s entire role set with one role. It does not change directory or application access.</p><div className="form-grid"><label>Member<select required value={target} onChange={e => setTarget(e.target.value)}><option value="">Choose a member</option>{members.filter(m => m.user_id !== session.user.id && m.active).map(m => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}</select></label><label>Proposed role<select value={role} onChange={e => setRole(e.target.value)}>{roleNames.map(r => <option key={r}>{r}</option>)}</select></label></div>
    {target && <div className="role-diff"><span>Current: {members.find(m => m.user_id === target)?.roles.join(', ')}</span><ChevronRight size={16}/><strong>Proposed: {role}</strong></div>}
    <label>Business justification<textarea required minLength={8} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} placeholder="Explain why this platform access is needed."/></label><button className="primary" disabled={busy}>Submit for independent review</button></form>}
    <section className="panel"><div className="section-heading"><h2>Role-change requests</h2><span>First 100 · newest first</span></div>{changes.length === 0 ? <p className="empty-text">No platform role changes have been proposed.</p> : changes.map(c => <article className="change" key={c.id}><div className="change-heading"><h3>{members.find(m => m.user_id === c.target_id)?.display_name || c.target_id}</h3><span className="pill">{new Date(c.expires_at) < new Date() && c.status !== 'EXECUTED' ? 'EXPIRED' : c.status}</span></div><p>{c.justification}</p><div className="role-diff"><span>{c.previous_roles.join(', ')}</span><ChevronRight size={15}/><strong>{c.roles.join(', ')}</strong></div><small>Expires {new Date(c.expires_at).toLocaleString()}</small><details><summary>Proposal evidence</summary><code>{c.digest}</code><p>Request {c.id}</p></details>
      {c.status === 'IN_REVIEW' && can('members:approve') && c.requester_id !== session.user.id && c.target_id !== session.user.id && <button className="secondary" disabled={busy} onClick={() => decide(c, 'approve')}>Approve exact proposal</button>}
      {c.status === 'APPROVED' && can('members:execute') && <button className="primary" disabled={busy} onClick={() => decide(c, 'execute')}>Execute approved role change</button>}</article>)}</section></>;
}

export function EnvironmentForm({ org, session }: { org: string; session: Session }) {
  const [name, setName] = useState(''); const [notice, setNotice] = useState(''); const [error, setError] = useState('');
  const create = async (event: React.FormEvent) => { event.preventDefault(); setError(''); setNotice(''); try {
    await api(`/organizations/${org}/environments`, 'POST', { name }, session.csrf_token); setNotice(`Sandbox environment "${name}" created. Select it in the top bar.`); setName('');
  } catch (e) { setError((e as Error).message); } };
  return <form className="panel proposal" onSubmit={create}><h2>Create a sandbox environment</h2><p>Sandbox environments isolate connector and simulation work. Production environments cannot be created here.</p>
    <label>Name<input className="text-input" aria-label="Environment name" required minLength={3} value={name} onChange={e => setName(e.target.value)}/></label>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}<button className="secondary">Create sandbox</button></form>;
}

export function AuditLog({ org }: { org: string }) {
  const [events, setEvents] = useState<Audit[]>([]); const [error, setError] = useState('');
  useEffect(() => { api<Audit[]>(`/organizations/${org}/audit`).then(setEvents).catch(e => setError(e.message)); }, [org]);
  return <section className="panel"><div className="section-heading"><h2>Platform audit trail</h2><span>Latest 100 records</span></div>{error && <p className="error" role="alert">{error}</p>}{events.length === 0 ? <p className="empty-text">No audit events are available.</p> : events.map(e => <details className="audit-event" key={e.id}><summary><span className="audit-icon"><ScrollText size={17}/></span><span><strong>{e.action}</strong><small>{new Date(e.created_at).toLocaleString()}</small></span><span className="ready-tag">{e.result}</span></summary><p>{e.justification}</p><dl><dt>Target</dt><dd>{e.target}</dd><dt>Correlation</dt><dd>{e.correlation_id}</dd></dl><pre>{JSON.stringify({ before: e.before_state, after: e.after_state }, null, 2)}</pre></details>)}</section>;
}
