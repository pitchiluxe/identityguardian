import type { ReactNode } from 'react';
import { ChevronRight, Network, Plug, ScrollText, ShieldCheck, Users } from 'lucide-react';
import { label, useResource } from '../api';
import type { Ctx, Envelope, Overview } from '../api';
import { Panel, SnapshotNote, State } from '../ui';
import { Access } from './Access';
import { Agents } from './Agents';
import { Administration, AuditLog, EnvironmentForm } from './Admin';
import { ChangeRequests, WhatIf } from './Changes';
import { Integrations } from './Integrations';
import { Investigate } from './Investigate';
import { JitAccess } from './Jit';
import { Labs } from './Labs';
import { Lifecycle } from './Lifecycle';
import { Machines } from './Machines';
import { AttackPaths } from './Paths';
import { Policies } from './Policies';
import { Radar } from './Radar';
import { Reports } from './Reports';
import { Reviews } from './Reviews';
import { TimeMachine } from './TimeMachine';
import { Applications, GraphExplorer, Identities } from './Twin';

export type PageDef = { subtitle: string; capability?: string; denied?: string; org?: boolean; render: (ctx: Ctx, overview: Overview) => ReactNode };

type FindingCounts = { counts: Record<string, number> };
type Summary = { counts: Record<string, number>; identities: number; relationships: number; terminated_identities: number };

function Dashboard({ ctx, overview }: { ctx: Ctx; overview: Overview }) {
  const summary = useResource<Envelope<Summary>>(ctx.env && ctx.can('identity:read') ? `${ctx.base}/summary` : null);
  const findings = useResource<Envelope<unknown[]> & FindingCounts>(ctx.env && ctx.can('findings:read') ? `${ctx.base}/findings` : null);
  return <>
    <div className="summary-grid"><div><span>Platform members</span><strong>{overview.member_count}</strong><small>Active organization memberships</small></div><div><span>Environment</span><strong className="text-stat">{ctx.envKind || 'Unassigned'}</strong><small>Synthetic data only</small></div><div><span>Your platform role</span><strong className="text-stat">{overview.roles.map(r => r.replaceAll('_', ' ')).join(', ')}</strong><small>Checked on every request</small></div></div>
    {ctx.can('identity:read') && <State {...summary}>{d => d.data.identities === 0 ? <div className="data-notice"><ShieldCheck size={17}/><span>No identity inventory has been ingested in this environment. An administrator can load the SYNTHETIC Contoso fixture and an operator can sync it from Integrations.</span></div> : <>
      <SnapshotNote snapshot={d.snapshot}/>
      <div className="metric-grid">{Object.entries(d.data.counts).sort().map(([k, v]) => <button key={k} className="metric" onClick={() => k.startsWith('identity:') ? ctx.navigate('Identities') : ['application', 'resource'].includes(k) ? ctx.navigate('Applications') : ctx.navigate('Identity graph')}><span>{label(k.replace('identity:', '') + (k.startsWith('identity:') ? ' identities' : 's'))}</span><strong>{v}</strong></button>)}
        <button className="metric" onClick={() => ctx.navigate('Identity graph')}><span>Relationships</span><strong>{d.data.relationships}</strong></button></div></>}</State>}
    {findings.data && <div className="metric-grid">{Object.entries(findings.data.counts).map(([rule, n]) => <button key={rule} className="metric" onClick={() => ctx.navigate('Privilege radar')}><span>{label(rule)} (rule-based)</span><strong>{n}</strong></button>)}</div>}
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
  'Privilege radar': { subtitle: 'Retained previous-role access, leavers, dormant privilege and unused entitlements.', capability: 'findings:read', render: ctx => <Radar {...ctx}/> },
  'Attack paths': { subtitle: 'Evidenced potential exposure to sensitive resources, with defensive controls.', capability: 'findings:read', render: ctx => <AttackPaths {...ctx}/> },
  'Access reviews': { subtitle: 'Evidence-backed certification. REMOVE creates a proposal; it never revokes.', capability: 'findings:read', render: ctx => <Reviews {...ctx}/> },
  'What-if simulator': { subtitle: 'Immutable overlays: residual routes, dependencies, lockouts and unknowns.', capability: 'access:read', render: ctx => <WhatIf {...ctx}/> },
  'Change requests': { subtitle: 'Exact proposals: simulate, independently approve, execute in the sandbox.', capability: 'findings:read', render: ctx => <ChangeRequests {...ctx}/> },
  'JIT access': { subtitle: 'Bounded temporary access with independent approval, native expiry and revocation tracking.', capability: 'findings:read', render: ctx => <JitAccess {...ctx}/> },
  'Machine identities': { subtitle: 'Owners, credential lifecycle metadata, dependencies and privileged access.', capability: 'identity:read', render: ctx => <Machines {...ctx}/> },
  'AI agents': { subtitle: 'Registered agents: declared scope versus effective access, expiry and observed activity.', capability: 'identity:read', render: ctx => <Agents {...ctx}/> },
  Lifecycle: { subtitle: 'Joiner baselines, mover retain/review/remove and leaver dependency plans.', capability: 'findings:read', render: ctx => <Lifecycle {...ctx}/> },
  'Time machine': { subtitle: 'What applied at a time, as known then versus as known now, with coverage.', capability: 'history:read', render: ctx => <TimeMachine {...ctx}/> },
  Investigations: { subtitle: 'Ask read-only questions; answers cite deterministic evidence.', capability: 'investigation:run', render: ctx => <Investigate {...ctx}/> },
  'AI assistant': { subtitle: 'Local model explanations of authorized evidence. Advisory only.', capability: 'investigation:run', render: ctx => <Investigate {...ctx}/> },
  Policies: { subtitle: 'Declarative policy versions: validate, test, simulate, approve, activate.', capability: 'findings:read', render: ctx => <Policies {...ctx}/> },
  Labs: { subtitle: 'Hands-on IAM exercises in isolated, learner-only LAB clones.', org: true, render: ctx => <Labs {...ctx}/> },
  Reports: { subtitle: 'Evidence-cited, redacted, expiring exports.', capability: 'report:read', render: ctx => <Reports {...ctx}/> },
  'Identity graph': { subtitle: 'Typed relationships around one node. Depth and size are bounded.', capability: 'graph:read', render: ctx => <GraphExplorer {...ctx}/> },
  Integrations: { subtitle: 'Sandbox connector, sync coverage and history.', capability: 'identity:read', render: ctx => <Integrations {...ctx}/> },
  Administration: { subtitle: 'Platform memberships and independent role changes.', capability: 'members:read', denied: 'Your current role cannot view or change platform memberships.', org: true, render: ctx => <><Administration org={ctx.org} session={ctx.session} can={ctx.can}/>{ctx.can('connector:manage') && <EnvironmentForm org={ctx.org} session={ctx.session}/>}</> },
  'Audit logs': { subtitle: 'Append-only platform audit trail.', capability: 'audit:read', denied: 'An auditor or organization administrator role is required.', org: true, render: ctx => <AuditLog org={ctx.org}/> },
};
