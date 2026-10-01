import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ShieldCheck, LayoutDashboard, Network, Users, KeyRound, Layers, Radar, Route,
  ClipboardCheck, Clock3, Bot, Cpu, GitBranch, FlaskConical, History, FileCheck2,
  Search, GraduationCap, FileText, ScrollText, Plug, Settings, Sparkles, ArrowUpRight,
  LockKeyhole, ChevronRight, LogOut, RefreshCw, Check, Menu, X, Info } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import './styles.css';

type Session = { user: { id: string; name: string }; organizations: { id: string; name: string }[]; csrf_token: string; amr: string[]; auth_time: number };
type Overview = { organization: { name: string }; environments: { name: string; kind: string }[]; member_count: number; roles: string[]; capabilities: string[]; identity_data: string };
type Member = { user_id: string; display_name: string; roles: string[]; version: number; active: boolean };
type Change = { id: string; target_id: string; requester_id: string; previous_roles: string[]; roles: string[]; justification: string; digest: string; status: string; expires_at: string };
type Audit = { id: string; action: string; target: string; created_at: string; result: string; justification: string; correlation_id: string; before_state: object; after_state: object };
const navigation: [string, LucideIcon, number][] = [
  ['Dashboard', LayoutDashboard, 1], ['Identity graph', Network, 2], ['Identities', Users, 2],
  ['Access', KeyRound, 3], ['Applications', Layers, 2], ['Privilege radar', Radar, 4],
  ['Attack paths', Route, 5], ['Access reviews', ClipboardCheck, 6], ['JIT access', Clock3, 8],
  ['Machine identities', Cpu, 9], ['AI agents', Bot, 10], ['Lifecycle', GitBranch, 11],
  ['What-if simulator', FlaskConical, 7], ['Time machine', History, 12], ['Policies', FileCheck2, 14],
  ['Investigations', Search, 13], ['Labs', GraduationCap, 15], ['Reports', FileText, 17],
  ['Audit logs', ScrollText, 1], ['Integrations', Plug, 16], ['Administration', Settings, 1], ['AI assistant', Sparkles, 13],
];
const roleNames = ['viewer', 'investigator', 'reviewer', 'approver', 'operator', 'org_admin', 'auditor', 'learner'];

async function api<T>(path: string, method = 'GET', body?: unknown, csrf?: string): Promise<T> {
  const response = await fetch('/api/v1' + path, { method, credentials: 'same-origin',
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(response.status === 401 ? 'Sign in to continue' : typeof data.detail === 'string' ? data.detail : 'Check the requested values and try again.');
  return data;
}

function Brand() { return <div className="brand"><span className="brand-mark"><ShieldCheck size={24}/></span><span>IdentityGuardian<span className="brand-ai">AI</span></span></div>; }

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [org, setOrg] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [page, setPage] = useState('Dashboard');
  const [menu, setMenu] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { api<Session>('/session').then(s => { setSession(s); setOrg(s.organizations[0]?.id || ''); })
    .catch(e => { if (e.message !== 'Sign in to continue') setError(e.message); }).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (!org) return; let current = true; setOverview(null); setError('');
    api<Overview>(`/organizations/${org}/overview`).then(v => { if (current) setOverview(v); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; }; }, [org, revision]);
  const navigate = (name: string) => { setPage(name); setMenu(false); };
  const signOut = async () => { try { await api('/auth/logout', 'POST', undefined, session?.csrf_token); setSession(null); setOverview(null); } catch (e) { setError((e as Error).message); } };
  if (loading) return <main className="loading"><ShieldCheck size={32}/><p>Opening your workspace…</p></main>;
  if (!session) return <div className="entry"><header><Brand/><span className="pill">Phase 1 foundation</span></header>
    <main className="entry-grid"><section className="entry-copy"><div className="eyeline"><span className="status-dot"/> Explainable identity security</div>
      <h1>Know the identity.<br/>Understand the access.</h1><p className="entry-description">The foundation for investigating access, following the evidence, and keeping consequential decisions in human hands.</p>
      <a className="primary login" href="/api/v1/auth/login">Sign in with your identity provider <ArrowUpRight size={18}/></a>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="entry-note"><LockKeyhole size={16}/><span>Organization-scoped access. No shared default password.</span></div>
    </section><section className="principle-panel" aria-label="Platform principles"><div className="panel-title"><ShieldCheck size={20}/><span>Trust begins with evidence</span></div>
      <div className="principle"><span className="step">01</span><div><h2>Understand the context</h2><p>One identity. Every relationship. A clear source for each conclusion.</p><span className="planned-tag">Identity intelligence · planned</span></div></div>
      <div className="principle"><span className="step">02</span><div><h2>Review the exact change</h2><p>Compare current and proposed platform roles before independent approval.</p><span className="ready-tag">Foundation workflow</span></div></div>
      <div className="principle"><span className="step">03</span><div><h2>Keep the record</h2><p>Record who changed platform access, why, and which approval permitted it.</p><span className="ready-tag">Audit foundation</span></div></div>
      <div className="panel-foot"><Info size={15}/> Local development · synthetic organization</div>
    </section></main><footer>IdentityGuardian AI <span>Investigate. Explain. Approve.</span></footer></div>;

  const can = (capability: string) => overview?.capabilities.includes(capability) ?? false;
  const phase = navigation.find(([name]) => name === page)?.[2] ?? 1;
  return <div className="workspace"><aside className={menu ? 'sidebar open' : 'sidebar'}><Brand/><div className="sidebar-label">Workspace</div>
    <nav aria-label="Main navigation">{navigation.map(([name, Icon, p], i) => <button key={name} onClick={() => navigate(name)} className={`${page === name ? 'active' : ''} ${i === 18 ? 'nav-break' : ''}`} aria-current={page === name ? 'page' : undefined}>
      <Icon size={17}/><span>{name}</span>{p > 1 && <span className="nav-planned" title={`Planned for Phase ${p}`}>Planned</span>}</button>)}</nav>
    <div className="sidebar-bottom"><span className="status-dot"/><div>Local foundation<small>No production connectors</small></div></div></aside>
    <div className="workspace-body"><header className="topbar"><button className="icon-button menu-button" aria-label="Toggle navigation" onClick={() => setMenu(!menu)}>{menu ? <X size={20}/> : <Menu size={20}/>}</button>
      <label className="org-selector"><span>Organization</span><select aria-label="Organization" value={org} onChange={e => setOrg(e.target.value)}>{session.organizations.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <span className="pill lab">{overview?.environments[0]?.kind || 'No environment'}</span><div className="topbar-person"><span className="avatar">{session.user.name.slice(0, 1)}</span><span>{session.user.name}</span><button className="icon-button" onClick={signOut} title="Sign out" aria-label="Sign out"><LogOut size={17}/></button></div></header>
      <main className="content"><div className="breadcrumb">Workspace <ChevronRight size={13}/><span>{page}</span></div>
        {error && <div className="error" role="alert">{error}</div>}
        {!org ? <Empty title="No organization assigned" text="Ask your platform administrator to provision your organization membership."/> : !overview ? <p role="status">Loading organization…</p> : <>
          <div className="page-heading"><div><h1>{page === 'Dashboard' ? 'Your identity workspace' : page}</h1><p>{page === 'Dashboard' ? 'A secure foundation. A clear view of what comes next.' : phase > 1 ? `Planned for Phase ${phase}. This capability is not implemented yet.` : 'Scoped to your selected organization.'}</p></div><button className="secondary" onClick={() => setRevision(v => v + 1)}><RefreshCw size={15}/> Refresh</button></div>
          {page === 'Dashboard' ? <><div className="foundation-banner"><div className="banner-icon"><ShieldCheck size={28}/></div><div><h2>Foundation workspace</h2><p>Manage platform access and inspect its audit trail. Identity ingestion begins in Phase 2.</p></div><span className="pill">Phase 1</span></div>
            <div className="summary-grid"><div><span>Platform members</span><strong>{overview.member_count}</strong><small>Active organization memberships</small></div><div><span>Environment</span><strong className="text-stat">{overview.environments[0]?.kind || 'Unassigned'}</strong><small>{overview.environments[0]?.name || 'No environment configured'}</small></div><div><span>Your platform role</span><strong className="text-stat">{overview.roles.map(r => r.replaceAll('_', ' ')).join(', ')}</strong><small>Checked on every request</small></div></div>
            <div className="dashboard-grid"><section className="panel"><div className="section-heading"><h2>Start with the foundation</h2><span>Available now</span></div>
              <button className="action-row" onClick={() => navigate('Administration')}><Users size={21}/><div><h3>Platform access</h3><p>Inspect members and review proposed role changes.</p></div><ChevronRight size={19}/></button>
              <button className="action-row" onClick={() => navigate('Audit logs')}><ScrollText size={21}/><div><h3>Audit evidence</h3><p>Follow the record of platform access decisions.</p></div><ChevronRight size={19}/></button>
              <div className="inset-note"><LockKeyhole size={17}/><span>High-risk role changes require recent verified MFA and an independent approver.</span></div></section>
            <section className="panel roadmap-panel"><div className="section-heading"><h2>The intelligence roadmap</h2><span>Planned</span></div>{[['Identity digital twin', 'Connect identities, groups and resources.', 2], ['Access explanations', 'Trace each permission to its source.', 3], ['Privilege radar', 'Find access retained from previous roles.', 4]].map(([title, text, p]) => <div className="roadmap-row" key={title}><span>{p}</span><div><h3>{title}</h3><p>{text}</p></div></div>)}</section></div>
            <div className="data-notice"><Info size={17}/><span>No identity inventory has been ingested. Exposure scores, attack paths and identity counts will appear when their evidence engines are implemented.</span></div></> :
          page === 'Administration' ? can('members:read') ? <Administration key={org+revision} org={org} session={session} can={can}/> : <Empty title="Restricted to authorized roles" text="Your current role cannot view or change platform memberships."/> :
          page === 'Audit logs' ? can('audit:read') ? <AuditLog key={org+revision} org={org}/> : <Empty title="Audit access is restricted" text="An auditor or organization administrator role is required."/> :
          <Empty title={`${page} is planned`} text={`This module is scheduled for Phase ${phase}. No ${page.toLowerCase()} results or integrations are being simulated on this page.`}/>}</>}
      </main><footer className="workspace-footer"><span>IdentityGuardian AI</span><span>Human authorization stays in control.</span></footer></div></div>;
}

function Empty({ title, text }: { title: string; text: string }) { return <section className="empty panel"><ShieldCheck size={32}/><h2>{title}</h2><p>{text}</p></section>; }

function Administration({ org, session, can }: { org: string; session: Session; can: (s: string) => boolean }) {
  const [members, setMembers] = useState<Member[]>([]); const [changes, setChanges] = useState<Change[]>([]);
  const [target, setTarget] = useState(''); const [role, setRole] = useState('viewer'); const [reason, setReason] = useState('');
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const base = `/organizations/${org}`;
  const refresh = async () => { const [m, c] = await Promise.all([api<Member[]>(base+'/members'), api<Change[]>(base+'/role-requests')]); setMembers(m); setChanges(c); };
  useEffect(() => { refresh().catch(e => setError(e.message)); }, [org]);
  const propose = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(''); setNotice(''); try {
    const member = members.find(m => m.user_id === target)!;
    await api(base+'/role-requests', 'POST', { target_id: target, roles: [role], justification: reason, expected_version: member.version, idempotency_key: crypto.randomUUID() }, session.csrf_token);
    setNotice('Proposal recorded. An independent approver must review the exact role replacement.'); setReason(''); await refresh();
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const decide = async (change: Change, action: string) => { setBusy(true); setError(''); setNotice(''); try {
    await api(base+`/role-requests/${change.id}/${action}`, 'POST', { digest: change.digest }, session.csrf_token);
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

function AuditLog({ org }: { org: string }) {
  const [events, setEvents] = useState<Audit[]>([]); const [error, setError] = useState('');
  useEffect(() => { api<Audit[]>(`/organizations/${org}/audit`).then(setEvents).catch(e => setError(e.message)); }, [org]);
  return <section className="panel"><div className="section-heading"><h2>Platform audit trail</h2><span>Latest 100 records</span></div>{error && <p className="error" role="alert">{error}</p>}{events.length === 0 ? <p className="empty-text">No audit events are available.</p> : events.map(e => <details className="audit-event" key={e.id}><summary><span className="audit-icon"><ScrollText size={17}/></span><span><strong>{e.action}</strong><small>{new Date(e.created_at).toLocaleString()}</small></span><span className="ready-tag">{e.result}</span></summary><p>{e.justification}</p><dl><dt>Target</dt><dd>{e.target}</dd><dt>Correlation</dt><dd>{e.correlation_id}</dd></dl><pre>{JSON.stringify({ before: e.before_state, after: e.after_state }, null, 2)}</pre></details>)}</section>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
