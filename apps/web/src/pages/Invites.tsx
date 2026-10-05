import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { api } from '../api';
import type { Session } from '../api';

type Invite = { id: string; email_normalized: string; roles: string[]; status: string; digest: string; inviter_id: string; expires_at: string; justification: string };
const roles = ['viewer', 'investigator', 'reviewer', 'auditor', 'learner', 'operator', 'approver', 'org_admin'];
const privileged = new Set(['operator', 'approver', 'org_admin']);

export function Invites({ org, session, can }: { org: string; session: Session; can: (c: string) => boolean }) {
  const [items, setItems] = useState<Invite[]>([]); const [email, setEmail] = useState(''); const [role, setRole] = useState('viewer');
  const [reason, setReason] = useState(''); const [link, setLink] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const base = `/organizations/${org}/invites`;
  const refresh = () => api<{ data: Invite[] }>(base).then(r => setItems(r.data)).catch(e => setError(e.message));
  useEffect(() => { refresh(); }, [org]);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(''); try { await fn(); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const submit = (e: React.FormEvent) => { e.preventDefault(); act(async () => {
    const r = await api<{ data: { link: string } }>(base, 'POST', { email, role, justification: reason }, session.csrf_token);
    setLink(window.location.origin + r.data.link); setEmail(''); setReason(''); }); };
  const status = (i: Invite) => (['ACTIVE', 'PENDING_APPROVAL'].includes(i.status) && new Date(i.expires_at) < new Date()) ? 'EXPIRED' : i.status;
  return <section className="panel"><div className="section-heading"><h2>Invites</h2><span>Invitees register their own password and one-time code</span></div><div className="pad">
    {can('members:propose') && <form className="proposal" onSubmit={submit}><div className="form-grid">
      <label>Email<input className="text-input" aria-label="Invite email" type="email" required value={email} onChange={e => setEmail(e.target.value)}/></label>
      <label>Role<select aria-label="Invite role" value={role} onChange={e => setRole(e.target.value)}>{roles.map(r => <option key={r}>{r}</option>)}</select></label></div>
      {privileged.has(role) && <p className="muted">Privileged role: an independent approver must approve before the link works.</p>}
      <label>Justification<textarea aria-label="Invite justification" required minLength={8} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>
      <button className="primary" disabled={busy}>Create invite</button></form>}
    {link && <div className="notice" role="status"><Check size={16}/><span>Copy this link now — it is shown only once and expires in 72 hours. Email delivery is planned, not implemented.</span>
      <code className="block">{link}</code><button className="secondary" onClick={() => navigator.clipboard?.writeText(link)}><Copy size={15}/> Copy link</button></div>}
    {error && <p className="error" role="alert">{error}</p>}
    {items.length === 0 ? <p className="empty-text">No invites yet.</p> : <div className="table-scroll"><table><thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Expires</th><th/></tr></thead><tbody>
      {items.map(i => <tr key={i.id}><td>{i.email_normalized}</td><td>{i.roles.join(', ')}</td><td><span className="pill">{status(i)}</span></td><td>{new Date(i.expires_at).toLocaleString()}</td><td className="button-row">
        {status(i) === 'PENDING_APPROVAL' && can('members:approve') && i.inviter_id !== session.user.id && <button className="secondary" disabled={busy} onClick={() => act(() => api(`${base}/${i.id}/decision`, 'POST', { digest: i.digest, decision: 'APPROVE' }, session.csrf_token))}>Approve</button>}
        {['ACTIVE', 'PENDING_APPROVAL'].includes(status(i)) && can('members:propose') && <button className="secondary" disabled={busy} onClick={() => act(() => api(`${base}/${i.id}/revoke`, 'POST', undefined, session.csrf_token))}>Revoke</button>}
      </td></tr>)}</tbody></table></div>}
  </div></section>;
}
