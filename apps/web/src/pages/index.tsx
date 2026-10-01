import type { ReactNode } from 'react';
import { ChevronRight, Network, Plug, ScrollText, ShieldCheck, Users } from 'lucide-react';
import { label, useResource } from '../api';
import type { Ctx, Envelope, Overview } from '../api';
import { Panel, SnapshotNote, State } from '../ui';
import { Access } from './Access';
import { Administration, AuditLog } from './Admin';
import { Integrations } from './Integrations';
import { Applications, GraphExplorer, Identities } from './Twin';

export type PageDef = { subtitle: string; capability?: string; denied?: string; org?: boolean; render: (ctx: Ctx, overview: Overview) => ReactNode };

type Summary = { counts: Record<string, number>; identities: number; relationships: number; terminated_identities: number };

function Dashboard({ ctx, overview }: { ctx: Ctx; overview: Overview }) {
  const summary = useResource<Envelope<Summary>>(ctx.env && ctx.can('identity:read') ? `${ctx.base}/summary` : null);
  return <>
    <div className="summary-grid"><div><span>Platform members</span><strong>{overview.member_count}</strong><small>Active organization memberships</small></div><div><span>Environment</span><strong className="text-stat">{ctx.envKind || 'Unassigned'}</strong><small>Synthetic data only</small></div><div><span>Your platform role</span><strong className="text-stat">{overview.roles.map(r => r.replaceAll('_', ' ')).join(', ')}</strong><small>Checked on every request</small></div></div>
    {ctx.can('identity:read') && <State {...summary}>{d => d.data.identities === 0 ? <div className="data-notice"><ShieldCheck size={17}/><span>No identity inventory has been ingested in this environment. An administrator can load the SYNTHETIC Contoso fixture and an operator can sync it from Integrations.</span></div> : <>
      <SnapshotNote snapshot={d.snapshot}/>
      <div className="metric-grid">{Object.entries(d.data.counts).sort().map(([k, v]) => <button key={k} className="metric" onClick={() => k.startsWith('identity:') ? ctx.navigate('Identities') : ['application', 'resource'].includes(k) ? ctx.navigate('Applications') : ctx.navigate('Identity graph')}><span>{label(k.replace('identity:', '') + (k.startsWith('identity:') ? ' identities' : 's'))}</span><strong>{v}</strong></button>)}
        <button className="metric" onClick={() => ctx.navigate('Identity graph')}><span>Relationships</span><strong>{d.data.relationships}</strong></button></div></>}</State>}
    <div className="dashboard-grid"><Panel title="Start investigating" meta="Available now">
      {ctx.can('identity:read') && <button className="action-row" onClick={() => ctx.navigate('Identities')}><Users size={21}/><div><h3>Identity inventory</h3><p>Profiles, attribute history and relationship provenance.</p></div><ChevronRight size={19}/></button>}
      {ctx.can('graph:read') && <button className="action-row" onClick={() => ctx.navigate('Identity graph')}><Network size={21}/><div><h3>Identity graph</h3><p>Explore typed relationships with bounded depth.</p></div><ChevronRight size={19}/></button>}
      <button className="action-row" onClick={() => ctx.navigate('Integrations')}><Plug size={21}/><div><h3>Sandbox integration</h3><p>Sync history and coverage.</p></div><ChevronRight size={19}/></button>
      {ctx.can('audit:read') && <button className="action-row" onClick={() => ctx.navigate('Audit logs')}><ScrollText size={21}/><div><h3>Audit evidence</h3><p>Follow the record of platform decisions.</p></div><ChevronRight size={19}/></button>}
    </Panel></div></>;
}

export const PAGES: Record<string, PageDef> = {
  Dashboard: { subtitle: 'Query-derived figures from one scoped snapshot.', org: true, render: (ctx, o) => <Dashboard ctx={ctx} overview={o}/> },
  Identities: { subtitle: 'Observed identities from the sandbox source, with provenance.', capability: 'identity:read', render: ctx => <Identities {...ctx}/> },
  Applications: { subtitle: 'Applications, resources, ownership and dependencies.', capability: 'identity:read', render: ctx => <Applications {...ctx}/> },
  Access: { subtitle: 'Effective access with every route, condition, deny and its evidence.', capability: 'access:read', render: ctx => <Access {...ctx}/> },
  'Identity graph': { subtitle: 'Typed relationships around one node. Depth and size are bounded.', capability: 'graph:read', render: ctx => <GraphExplorer {...ctx}/> },
  Integrations: { subtitle: 'Sandbox connector, sync coverage and history.', capability: 'identity:read', render: ctx => <Integrations {...ctx}/> },
  Administration: { subtitle: 'Platform memberships and independent role changes.', capability: 'members:read', denied: 'Your current role cannot view or change platform memberships.', org: true, render: ctx => <Administration org={ctx.org} session={ctx.session} can={ctx.can}/> },
  'Audit logs': { subtitle: 'Append-only platform audit trail.', capability: 'audit:read', denied: 'An auditor or organization administrator role is required.', org: true, render: ctx => <AuditLog org={ctx.org}/> },
};
