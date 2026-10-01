import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ShieldCheck, LayoutDashboard, Network, Users, KeyRound, Layers, Radar, Route,
  ClipboardCheck, Clock3, Bot, Cpu, GitBranch, FlaskConical, History, FileCheck2,
  Search, GraduationCap, FileText, ScrollText, Plug, Settings, Sparkles, ArrowUpRight,
  LockKeyhole, ChevronRight, LogOut, RefreshCw, Menu, X, Info } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api, useResource } from './api';
import type { Ctx, Environment, Envelope, Overview, Session } from './api';
import { Empty } from './ui';
import { PAGES } from './pages';

type NavItem = [name: string, icon: LucideIcon, phase: number, group: string];
const navigation: NavItem[] = [
  ['Dashboard', LayoutDashboard, 1, 'Overview'], ['Identities', Users, 2, 'Overview'], ['Applications', Layers, 2, 'Overview'],
  ['Access', KeyRound, 3, 'Overview'], ['Identity graph', Network, 2, 'Overview'],
  ['Privilege radar', Radar, 4, 'Intelligence'], ['Attack paths', Route, 5, 'Intelligence'], ['Investigations', Search, 13, 'Intelligence'], ['Time machine', History, 12, 'Intelligence'],
  ['Access reviews', ClipboardCheck, 6, 'Governance'], ['JIT access', Clock3, 8, 'Governance'], ['Lifecycle', GitBranch, 11, 'Governance'], ['What-if simulator', FlaskConical, 7, 'Governance'], ['Change requests', FileCheck2, 8, 'Governance'], ['Policies', FileCheck2, 14, 'Governance'],
  ['Machine identities', Cpu, 9, 'Non-human'], ['AI agents', Bot, 10, 'Non-human'],
  ['Labs', GraduationCap, 15, 'Learning'],
  ['Reports', FileText, 17, 'Operations'], ['Audit logs', ScrollText, 1, 'Operations'], ['Integrations', Plug, 2, 'Operations'], ['Administration', Settings, 1, 'Operations'], ['AI assistant', Sparkles, 13, 'Operations'],
];
export const BUILD_LABEL = 'Local build · synthetic data';

function Brand() { return <div className="brand"><span className="brand-mark"><ShieldCheck size={24}/></span><span>IdentityGuardian<span className="brand-ai">AI</span></span></div>; }

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [org, setOrg] = useState('');
  const [env, setEnv] = useState('');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [page, setPage] = useState('Dashboard');
  const [params, setParams] = useState<Record<string, string>>({});
  const [menu, setMenu] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { api<Session>('/session').then(s => { setSession(s); setOrg(s.organizations[0]?.id || ''); })
    .catch(e => { if (e.message !== 'Sign in to continue') setError(e.message); }).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (!org) return; let current = true; setOverview(null); setError('');
    api<Overview>(`/organizations/${org}/overview`).then(v => { if (current) setOverview(v); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; }; }, [org, revision]);
  const envs = useResource<Envelope<Environment[]>>(org && overview ? `/organizations/${org}/environments` : null, [revision]);
  useEffect(() => { const list = envs.data?.data || []; if (list.length && !list.some(e => e.id === env)) setEnv(list[0].id); }, [envs.data]);
  const envCapabilities = useResource<Envelope<string[]>>(org && env ? `/organizations/${org}/environments/${env}/capabilities` : null, [revision]);
  const navigate = (name: string, next: Record<string, string> = {}) => { setPage(name); setParams(next); setMenu(false); window.scrollTo?.(0, 0); };
  const signOut = async () => { try { await api('/auth/logout', 'POST', undefined, session?.csrf_token); setSession(null); setOverview(null); } catch (e) { setError((e as Error).message); } };
  if (loading) return <main className="loading"><ShieldCheck size={32}/><p>Opening your workspace…</p></main>;
  if (!session) return <Landing error={error}/>;

  const envCaps = envCapabilities.data?.data;
  const can = (capability: string) => (envCaps ?? overview?.capabilities ?? []).includes(capability);
  const environment = envs.data?.data.find(e => e.id === env);
  const item = navigation.find(([name]) => name === page) || navigation[0];
  const ctx: Ctx = { org, env, session, can, base: `/organizations/${org}/environments/${env}`, envKind: environment?.kind || '', navigate, params, selectEnv: (id: string) => { setEnv(id); setRevision(v => v + 1); } };
  const renderer = PAGES[page];
  let body: ReactNode;
  if (!org) body = <Empty title="No organization assigned" text="Ask your platform administrator to provision your organization membership."/>;
  else if (!overview) body = <p role="status">Loading organization…</p>;
  else if (renderer && (renderer.org || env)) body = renderer.capability && !can(renderer.capability)
    ? <Empty title="Restricted to authorized roles" text={renderer.denied || 'Your current platform role does not include this capability.'}/>
    : renderer.render(ctx, overview);
  else if (renderer) body = <Empty title="No environment" text="This organization has no environment yet."/>;
  else body = <Empty title={`${page} is planned`} text={`This module is scheduled for Phase ${item[2]}. No ${page.toLowerCase()} results or integrations are simulated on this page.`}/>;

  let lastGroup = '';
  return <div className="workspace"><aside className={menu ? 'sidebar open' : 'sidebar'}><Brand/>
    <nav aria-label="Main navigation">{navigation.map(([name, Icon, phase, group]) => { const header = group !== lastGroup; lastGroup = group; return <div key={name}>{header && <div className="sidebar-label">{group}</div>}<button onClick={() => navigate(name)} className={page === name ? 'active' : ''} aria-current={page === name ? 'page' : undefined}>
      <Icon size={17}/><span>{name}</span>{!PAGES[name] && <span className="nav-planned" title={`Planned for Phase ${phase}`}>Planned</span>}</button></div>; })}</nav>
    <div className="sidebar-bottom"><span className="status-dot"/><div>{BUILD_LABEL}<small>No production connectors</small></div></div></aside>
    <div className="workspace-body"><header className="topbar"><button className="icon-button menu-button" aria-label="Toggle navigation" onClick={() => setMenu(!menu)}>{menu ? <X size={20}/> : <Menu size={20}/>}</button>
      <label className="org-selector"><span>Organization</span><select aria-label="Organization" value={org} onChange={e => { setOrg(e.target.value); setEnv(''); }}>{session.organizations.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <label className="org-selector"><span>Environment</span><select aria-label="Environment" value={env} onChange={e => setEnv(e.target.value)}>{(envs.data?.data || []).map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
      <span className="pill lab">{environment?.kind || 'No environment'}</span>
      <span className="freshness">{environment ? environment.last_sync ? `Synced ${new Date(environment.last_sync).toLocaleString()}` : 'Never synced' : ''}</span>
      <div className="topbar-person"><span className="avatar">{session.user.name.slice(0, 1)}</span><span>{session.user.name}</span><button className="icon-button" onClick={signOut} title="Sign out" aria-label="Sign out"><LogOut size={17}/></button></div></header>
      <main className="content"><div className="breadcrumb">Workspace <ChevronRight size={13}/><span>{page}</span></div>
        {error && <div className="error" role="alert">{error}</div>}
        {overview && <div className="page-heading"><div><h1>{page === 'Dashboard' ? 'Your identity workspace' : page}</h1><p>{renderer ? renderer.subtitle : `Planned for Phase ${item[2]}. This capability is not implemented yet.`}</p></div><button className="secondary" onClick={() => setRevision(v => v + 1)}><RefreshCw size={15}/> Refresh</button></div>}
        <div key={`${org}:${env}:${revision}:${page}:${JSON.stringify(params)}`}>{body}</div>
      </main><footer className="workspace-footer"><span>IdentityGuardian AI</span><span>Human authorization stays in control.</span></footer></div></div>;
}

function Landing({ error }: { error: string }) {
  return <div className="entry"><header><Brand/><span className="pill">{BUILD_LABEL}</span></header>
    <main className="entry-grid"><section className="entry-copy"><div className="eyeline"><span className="status-dot"/> Explainable identity security</div>
      <h1>Know the identity.<br/>Understand the access.</h1><p className="entry-description">Investigate access, follow the evidence, and keep consequential decisions in human hands.</p>
      <a className="primary login" href="/api/v1/auth/login">Sign in with your identity provider <ArrowUpRight size={18}/></a>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="entry-note"><LockKeyhole size={16}/><span>Organization-scoped access. No shared default password.</span></div>
    </section><section className="principle-panel" aria-label="Platform principles"><div className="panel-title"><ShieldCheck size={20}/><span>Trust begins with evidence</span></div>
      <div className="principle"><span className="step">01</span><div><h2>Understand the context</h2><p>One identity. Every relationship. A source for each conclusion.</p></div></div>
      <div className="principle"><span className="step">02</span><div><h2>Review the exact change</h2><p>Simulate impact, then require an independent approver for the exact proposal.</p></div></div>
      <div className="principle"><span className="step">03</span><div><h2>Keep the record</h2><p>Record who changed access, why, and which approval permitted it.</p></div></div>
      <div className="panel-foot"><Info size={15}/> Local development · synthetic organization</div>
    </section></main><footer>IdentityGuardian AI <span>Investigate. Explain. Approve.</span></footer></div>;
}
