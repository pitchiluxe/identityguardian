import { useState } from 'react';
import { Bot } from 'lucide-react';
import { fmt, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { KV, Panel, SnapshotNote, State, Tag } from '../ui';

type Agent = { identity: TwinNode; owners: TwinNode[]; credentials: TwinNode[];
  declared: { owner: string; department: string; model: string; purpose: string; maximum_privilege: string; credential_scope: string; expires_at: string; allowed_tools: string[]; allowed_data: string[]; prohibited_data: string[] };
  effective: { tools: string[]; data: Record<string, string[]>; entitlements: number }; excess_tools: string[]; excess_data: string[]; prohibited_access: string[];
  expiry: { expires_at: string; days_left: number | null; state: string }; activity: { target: string; events: number; last: string }[] };

export function Agents(ctx: Ctx) {
  const [tool, setTool] = useState(''); const [data, setData] = useState('');
  const q = new URLSearchParams({ ...(tool ? { tool } : {}), ...(data ? { data_classification: data } : {}) });
  const agents = useResource<Envelope<Agent[]>>(`${ctx.base}/agents?${q}`);
  return <><div className="toolbar"><label className="inline">Can use tool<input aria-label="Tool filter" placeholder="e.g. email.send" value={tool} onChange={e => setTool(e.target.value.trim())}/></label>
    <label className="inline">Can reach data class<select aria-label="Data class filter" value={data} onChange={e => setData(e.target.value)}><option value="">Any</option>{['customer-data', 'payroll', 'financial', 'source-code', 'backups'].map(d => <option key={d}>{d}</option>)}</select></label></div>
    <State {...agents}>{d => <><SnapshotNote snapshot={d.snapshot}/><Panel title="Registered AI agents" meta={`${d.data.length} · ${String(d.rules_version)}`}>{d.data.length === 0 ? <p className="empty-text">No agents match.</p> : d.data.map(a => <details className="finding" key={a.identity.id} open>
      <summary><h3 style={{ display: 'inline-flex' }}><Bot size={16}/>{a.identity.name}<Tag tone={a.expiry.state === 'VALID' ? 'ok' : a.expiry.state === 'EXPIRED' ? 'critical' : 'warn'}>{a.expiry.state}</Tag>{a.prohibited_access.length > 0 && <Tag tone="critical">Prohibited data reachable</Tag>}{(a.excess_tools.length + a.excess_data.length) > 0 && <Tag tone="warn">Exceeds declared scope</Tag>}</h3></summary>
      <KV rows={[['Owner', a.owners.map(o => o.name).join(', ') || 'None'], ['Department', a.declared.department], ['Model', a.declared.model], ['Purpose', a.declared.purpose], ['Maximum privilege (declared)', a.declared.maximum_privilege], ['Credential scope', a.declared.credential_scope], ['Registration expires', `${fmt(a.expiry.expires_at)}${a.expiry.days_left !== null ? ` (${a.expiry.days_left} days)` : ''}`]]}/>
      <div className="diff-grid"><div><small>Tools · declared</small><p>{a.declared.allowed_tools.join(', ') || '—'}</p><small>Tools · effective</small><p>{a.effective.tools.join(', ') || '—'}</p>{a.excess_tools.length > 0 && <Tag tone="warn">Undeclared: {a.excess_tools.join(', ')}</Tag>}</div>
        <div><small>Data · declared</small><p>{a.declared.allowed_data.join(', ') || '—'}</p><small>Data · effective</small><p>{Object.entries(a.effective.data).map(([k, v]) => `${k} (${v.join(', ')})`).join('; ') || '—'}</p>{a.excess_data.length > 0 && <Tag tone="warn">Undeclared: {a.excess_data.join(', ')}</Tag>}</div>
        <div><small>Prohibited data</small><p>{a.declared.prohibited_data.join(', ') || '—'}</p>{a.prohibited_access.length > 0 && <Tag tone="critical">Reachable: {a.prohibited_access.join(', ')}</Tag>}</div>
        <div><small>Observed activity (within coverage)</small>{a.activity.length === 0 ? <p>No observed activity</p> : <ul>{a.activity.map(x => <li key={x.target}>{x.target}: {x.events} events, last {fmt(x.last)}</li>)}</ul>}</div></div>
      <div className="button-row">{ctx.can('access:read') && <button className="secondary" onClick={() => ctx.navigate('Access', { node: a.identity.external_id })}>Explain effective access</button>}</div></details>)}</Panel></>}</State></>;
}
