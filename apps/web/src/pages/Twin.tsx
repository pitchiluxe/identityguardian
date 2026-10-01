import { useMemo, useState } from 'react';
import { ArrowLeft, Network, Search } from 'lucide-react';
import { fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinEdge, TwinNode } from '../api';
import { KV, Panel, SnapshotNote, State, Tag } from '../ui';
import { TimelinePanel } from './Radar';

type Related = TwinEdge & { direction: 'in' | 'out'; other: TwinNode };
type Profile = { node: TwinNode; relationships: Related[]; history: { name: string; status: string; attributes: Record<string, unknown>; valid_from: string; valid_to: string | null; recorded_from: string; recorded_to: string | null }[] };
const KIND_COLORS: Record<string, string> = { identity: '#71d9da', group: '#9fb6ff', role: '#c6a4ff', permission: '#f1cc87', resource: '#ff9f8f', application: '#ffb46b', account: '#8fb3c9', department: '#7f93a8', credential: '#e7d36f', tool: '#a8e6a1', device: '#8aa0b5', provider: '#b0c4d8' };

export function statusTone(status: string) { return status === 'terminated' ? 'critical' : status === 'active' ? 'ok' : 'neutral'; }

export function Identities(ctx: Ctx) {
  const [q, setQ] = useState(''); const [subtype, setSubtype] = useState(''); const [cursor, setCursor] = useState<string[]>([]);
  const params = new URLSearchParams({ limit: '25', ...(q ? { q } : {}), ...(subtype ? { subtype } : {}), ...(cursor.length ? { cursor: cursor[cursor.length - 1] } : {}) });
  const list = useResource<Envelope<TwinNode[]>>(`${ctx.base}/identities?${params}`);
  if (ctx.params.node) return <IdentityProfile {...ctx}/>;
  return <Panel title="Identity inventory" meta="Current effective state · 25 per page">
    <div className="toolbar"><label className="search"><Search size={15}/><input aria-label="Search identities" placeholder="Search by name" value={q} onChange={e => { setQ(e.target.value); setCursor([]); }}/></label>
      <label className="inline">Type<select value={subtype} onChange={e => { setSubtype(e.target.value); setCursor([]); }}><option value="">All</option>{['employee', 'contractor', 'guest', 'admin', 'machine', 'agent'].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label></div>
    <State {...list} empty="No identities have been ingested for this environment. Load the synthetic fixture and run a sync from Integrations.">{d => d.data.length === 0 ? <p className="empty-text">No identities match.</p> : <><div className="table-scroll"><table><thead><tr><th>Identity</th><th>Type</th><th>Department</th><th>Status</th><th>MFA</th></tr></thead><tbody>
      {d.data.map(n => <tr key={n.id}><td><button className="link" onClick={() => ctx.navigate('Identities', { node: n.external_id })}>{n.name}</button><small className="mono block">{n.external_id}</small></td><td>{label(n.subtype)}</td><td>{fmt(n.attributes.department)}</td><td><Tag tone={statusTone(n.status)}>{n.status}</Tag></td><td>{n.attributes.mfa_registered === undefined ? '—' : n.attributes.mfa_registered ? 'Registered' : <Tag tone="warn">None</Tag>}</td></tr>)}
    </tbody></table></div><div className="pager">{cursor.length > 0 && <button className="secondary" onClick={() => setCursor(cursor.slice(0, -1))}>Previous</button>}{d.next_cursor && <button className="secondary" onClick={() => setCursor([...cursor, d.next_cursor!])}>Next</button>}</div></>}</State></Panel>;
}

export function IdentityProfile(ctx: Ctx) {
  const node = ctx.params.node;
  const profile = useResource<Envelope<Profile>>(`${ctx.base}/nodes/${encodeURIComponent(node)}`);
  return <><button className="secondary back" onClick={() => ctx.navigate('Identities')}><ArrowLeft size={15}/>All identities</button>
    <State {...profile}>{d => { const p = d.data; const groups: Record<string, Related[]> = {};
      p.relationships.forEach(r => { (groups[r.classification] ||= []).push(r); });
      return <><div className="profile-head panel"><div><h2>{p.node.name}</h2><p className="mono">{p.node.external_id} · {label(p.node.kind)} · {label(p.node.subtype)}</p></div><div className="tags"><Tag tone={statusTone(p.node.status)}>{p.node.status}</Tag>{Boolean(p.node.attributes.synthetic) && <Tag tone="warn">SYNTHETIC</Tag>}
        {ctx.can('graph:read') && <button className="secondary" onClick={() => ctx.navigate('Identity graph', { node: p.node.external_id })}><Network size={15}/>Open in graph</button>}
        {ctx.can('access:read') && p.node.kind === 'identity' && <button className="primary" onClick={() => ctx.navigate('Access', { node: p.node.external_id })}>Explain access</button>}</div></div>
        <SnapshotNote snapshot={d.snapshot}/>
        <div className="two-col"><Panel title="Attributes" meta="Current revision"><KV rows={Object.entries(p.node.attributes)}/></Panel>
          <Panel title="Attribute history" meta="Effective and knowledge time">{p.history.map((h, i) => <div className="history-row" key={i}><strong>{fmt(h.attributes.department)} · {fmt(h.attributes.title)}</strong><small>Effective {fmt(h.valid_from)} → {h.valid_to ? fmt(h.valid_to) : 'open'} · known {fmt(h.recorded_from)}{h.recorded_to ? ` → superseded ${fmt(h.recorded_to)}` : ''}</small></div>)}</Panel></div>
        {ctx.can('history:read') && p.node.kind === 'identity' && <TimelinePanel ctx={ctx} node={p.node.external_id}/>}
        {Object.entries(groups).map(([cls, rows]) => <Panel key={cls} title={`${label(cls)} relationships`} meta={`${rows.length} current`}><div className="table-scroll"><table><thead><tr><th>Relationship</th><th>Related</th><th>Origin / ticket</th><th>Since</th><th>Evidence</th></tr></thead><tbody>
          {rows.map(r => <tr key={r.id}><td>{r.direction === 'out' ? label(r.type) : `${label(r.type)} (incoming)`}</td><td><button className="link" onClick={() => r.other.kind === 'identity' ? ctx.navigate('Identities', { node: r.other.external_id }) : ctx.navigate('Identity graph', { node: r.other.external_id })}>{r.other.name}</button><small className="block">{label(r.other.kind)}</small></td><td>{fmt(r.attributes.origin)}{r.attributes.ticket ? ` · ${r.attributes.ticket}` : ''}{Array.isArray(r.attributes.conditions) && <small className="block">Conditions: {(r.attributes.conditions as { type: string }[]).map(c => c.type).join(', ')}</small>}</td><td>{fmt(r.valid_from)}</td><td className="mono small">{r.evidence_id.slice(0, 8)}</td></tr>)}
        </tbody></table></div></Panel>)}</>; }}</State></>;
}

type Hood = { nodes: TwinNode[]; edges: TwinEdge[]; complete: boolean; truncation_reason: string | null; collapsed: { id: string; name: string; degree: number }[] };

export function GraphExplorer(ctx: Ctx) {
  const [focus, setFocus] = useState(ctx.params.node || 'idn-erick'); const [depth, setDepth] = useState(2);
  const [classes, setClasses] = useState<Record<string, boolean>>({ grant: true, deny: true, exposure: true, context: false, dependency: true });
  const hood = useResource<Envelope<Hood>>(`${ctx.base}/graph/neighbors?node=${encodeURIComponent(focus)}&depth=${depth}&max_nodes=120`);
  return <><div className="toolbar"><label className="inline">Focus<input aria-label="Focus node external ID" className="mono" value={focus} onChange={e => setFocus(e.target.value.trim())}/></label>
    <label className="inline">Depth<select value={depth} onChange={e => setDepth(Number(e.target.value))}>{[1, 2, 3].map(d => <option key={d}>{d}</option>)}</select></label>
    <fieldset className="filters"><legend>Relationship classes</legend>{Object.keys(classes).map(c => <label key={c} className="check"><input type="checkbox" checked={classes[c]} onChange={e => setClasses({ ...classes, [c]: e.target.checked })}/>{label(c)}</label>)}</fieldset></div>
    <State {...hood}>{d => <GraphView ctx={ctx} data={d} classes={classes} onFocus={setFocus} focus={focus}/>}</State></>;
}

function GraphView({ ctx, data, classes, onFocus, focus }: { ctx: Ctx; data: Envelope<Hood>; classes: Record<string, boolean>; onFocus: (id: string) => void; focus: string }) {
  const { nodes, edges, center } = useMemo(() => {
    const edges = data.data.edges.filter(e => classes[e.classification]);
    const center = data.data.nodes.find(n => n.external_id === focus || n.id === focus) || data.data.nodes[0];
    const dist: Record<string, number> = { [center.id]: 0 }; let frontier = [center.id];
    while (frontier.length) { const next: string[] = []; for (const id of frontier) for (const e of edges) { const other = e.src === id ? e.dst : e.dst === id ? e.src : null; if (other && dist[other] === undefined) { dist[other] = dist[id] + 1; next.push(other); } } frontier = next; }
    const visible = data.data.nodes.filter(n => dist[n.id] !== undefined);
    const rings: Record<number, TwinNode[]> = {}; visible.forEach(n => { (rings[dist[n.id]] ||= []).push(n); });
    const pos: Record<string, [number, number]> = {};
    Object.entries(rings).forEach(([r, list]) => { const radius = Number(r) * 170; list.sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name)).forEach((n, i) => { const a = (i / list.length) * Math.PI * 2 + Number(r) * 0.4; pos[n.id] = [radius * Math.cos(a), radius * Math.sin(a)]; }); });
    return { nodes: visible.map(n => ({ ...n, x: pos[n.id][0], y: pos[n.id][1] })), edges: edges.filter(e => pos[e.src] && pos[e.dst]).map(e => ({ ...e, a: pos[e.src], b: pos[e.dst] })), center };
  }, [data, classes, focus]);
  const extent = Math.max(260, ...nodes.map(n => Math.max(Math.abs(n.x), Math.abs(n.y)) + 90));
  const name = (id: string) => data.data.nodes.find(n => n.id === id)?.name || id;
  return <><SnapshotNote snapshot={data.snapshot} completeness={data.completeness}/>{!data.data.complete && <div className="warning" role="note">Partial neighbourhood: {data.data.truncation_reason}. Missing nodes are not proof of absent relationships.</div>}
    {data.data.collapsed.length > 0 && <div className="snapshot-note">Not expanded (high-degree hubs): {data.data.collapsed.map(c => <button key={c.id} className="link" onClick={() => onFocus(data.data.nodes.find(n => n.id === c.id)!.external_id)}>{c.name} ({c.degree})</button>)} — focus a hub to see all its relationships.</div>}
    <section className="panel graph-panel"><svg viewBox={`${-extent} ${-extent} ${extent * 2} ${extent * 2}`} role="img" aria-label={`Relationship graph around ${center.name}`}>
      <defs><marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#5d7690"/></marker></defs>
      {edges.map(e => <line key={e.id} x1={e.a[0]} y1={e.a[1]} x2={e.b[0]} y2={e.b[1]} className={`edge edge-${e.classification}`} markerEnd="url(#arrow)"><title>{`${name(e.src)} → ${e.type} → ${name(e.dst)}`}</title></line>)}
      {nodes.map(n => <g key={n.id} transform={`translate(${n.x},${n.y})`} className="gnode" tabIndex={0} role="button" aria-label={`${n.name}, ${n.kind}. Focus`} onClick={() => onFocus(n.external_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onFocus(n.external_id); }}>
        <circle r={n.id === center.id ? 17 : 12} fill={KIND_COLORS[n.kind] || '#9aaabb'} stroke={n.status === 'terminated' ? '#ff8f80' : '#0a1423'} strokeWidth={3}/><text y={28} textAnchor="middle">{n.name.length > 26 ? n.name.slice(0, 25) + '…' : n.name}</text></g>)}
    </svg><div className="legend">{Object.entries(KIND_COLORS).map(([k, c]) => <span key={k}><i style={{ background: c }}/>{k}</span>)}</div></section>
    <Panel title="Relationships (accessible table)" meta={`${edges.length} shown`}><div className="table-scroll"><table><thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Class</th><th>Evidence</th></tr></thead><tbody>
      {edges.map(e => <tr key={e.id}><td><button className="link" onClick={() => onFocus(data.data.nodes.find(n => n.id === e.src)!.external_id)}>{name(e.src)}</button></td><td>{label(e.type)}{e.attributes.ticket ? <small className="block">{String(e.attributes.ticket)}</small> : null}</td><td><button className="link" onClick={() => onFocus(data.data.nodes.find(n => n.id === e.dst)!.external_id)}>{name(e.dst)}</button></td><td><Tag tone={e.classification === 'exposure' || e.classification === 'deny' ? 'warn' : 'neutral'}>{e.classification}</Tag></td><td className="mono small">{e.evidence_id.slice(0, 8)}</td></tr>)}
    </tbody></table></div>{ctx.can('identity:read') && center.kind === 'identity' && <div className="panel-actions"><button className="secondary" onClick={() => ctx.navigate('Identities', { node: center.external_id })}>Open {center.name} profile</button></div>}</Panel></>;
}

type App = TwinNode & { direct_grants: number; depends_on: string[] };
export function Applications(ctx: Ctx) {
  const apps = useResource<Envelope<App[]>>(`${ctx.base}/applications`);
  return <State {...apps} empty="No applications ingested.">{d => <Panel title="Applications and resources" meta={`${d.data.length} current`}><div className="table-scroll"><table><thead><tr><th>Name</th><th>Kind</th><th>Sensitivity</th><th>Owner</th><th>Direct grants</th><th>Depends on</th></tr></thead><tbody>
    {d.data.map(a => <tr key={a.id}><td><button className="link" onClick={() => ctx.navigate('Identity graph', { node: a.external_id })}>{a.name}</button></td><td>{label(a.kind)} · {a.subtype}</td><td><Tag tone={a.attributes.sensitivity === 'critical' ? 'critical' : a.attributes.sensitivity === 'high' ? 'warn' : 'neutral'}>{fmt(a.attributes.sensitivity)}</Tag></td><td>{a.attributes.owner ? fmt(a.attributes.owner) : <Tag tone="warn">No owner</Tag>}</td><td>{a.direct_grants}</td><td>{a.depends_on.join(', ') || '—'}</td></tr>)}
  </tbody></table></div></Panel>}</State>;
}
