import { useState } from 'react';
import { ArrowLeft, Check } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinNode } from '../api';
import { Panel, State, Tag, Warning } from '../ui';
import { statusTone } from './Changes';

type Event = { id: string; kind: string; effective_at: string; details: Record<string, string>; workflow_id: string | null; identity: TwinNode | null };
type Action = { kind: string; label: string; rationale: string; proposal: Record<string, string> | null; evidence_ids: string[]; decision: string | null };
type Plan = { status: string; actions: Action[]; identity: TwinNode; event: { kind: string; effective_at: string; details: Record<string, string> }; note?: string; baseline?: { version: number; groups: string[] } | null; rules_version: string };
type Baseline = { id: string; department: string; groups: string[]; version: number; status: string; proposed_by: string; proposed_by_name: string; approved_by_name: string | null; justification: string };
type Workflow = { workflow: { id: string; kind: string }; changes: { id: string; kind: string; status: string; justification: string }[]; status: string };
const tone = (d: string | null) => d === 'REMOVE' || d === 'DISABLE' ? 'critical' : d === 'REVIEW' || d === 'TRANSFER' || d === 'ROTATE' ? 'warn' : d === 'RETAIN' ? 'ok' : 'info';

export function Lifecycle(ctx: Ctx) {
  const events = useResource<Envelope<Event[]>>(`${ctx.base}/lifecycle/events`);
  if (ctx.params.event) return <EventPlan ctx={ctx} id={ctx.params.event} workflow={ctx.params.workflow}/>;
  return <><Baselines ctx={ctx}/>
    <State {...events}>{d => <Panel title="Employment events" meta={`${d.data.length} from the HR source`}><div className="table-scroll"><table><thead><tr><th>Event</th><th>Identity</th><th>Effective</th><th>Details</th><th>Workflow</th></tr></thead><tbody>
      {d.data.map(e => <tr key={e.id}><td><button className="link" onClick={() => ctx.navigate('Lifecycle', { event: e.id, ...(e.workflow_id ? { workflow: e.workflow_id } : {}) })}>{label(e.kind)}</button></td><td>{e.identity?.name || '—'}</td><td>{fmt(e.effective_at)}</td><td>{Object.entries(e.details).map(([k, v]) => `${label(k)}: ${v}`).join(' · ')}</td><td>{e.workflow_id ? <Tag tone="info">Started</Tag> : '—'}</td></tr>)}
    </tbody></table></div></Panel>}</State></>;
}

function Baselines({ ctx }: { ctx: Ctx }) {
  const rows = useResource<Envelope<Baseline[]>>(`${ctx.base}/lifecycle/baselines`);
  const [dept, setDept] = useState('Finance'); const [groups, setGroups] = useState('grp-finance-analysts, grp-all-staff'); const [why, setWhy] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setError(''); try { await fn(); rows.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <Panel title="Joiner baselines" meta="Independently approved; only APPROVED baselines are used">
    <State {...rows}>{d => d.data.length === 0 ? <p className="empty-text">No baselines. Joiners are not provisioned until a baseline is approved.</p> : <div className="table-scroll"><table><thead><tr><th>Department</th><th>Groups</th><th>Version</th><th>Status</th><th>Proposed / approved</th><th></th></tr></thead><tbody>
      {d.data.map(b => <tr key={b.id}><td>{b.department}</td><td className="mono">{b.groups.join(', ')}</td><td>v{b.version}</td><td><Tag tone={b.status === 'APPROVED' ? 'ok' : b.status === 'PROPOSED' ? 'info' : 'neutral'}>{b.status}</Tag></td><td>{b.proposed_by_name}{b.approved_by_name ? ` / ${b.approved_by_name}` : ''}</td>
        <td>{b.status === 'PROPOSED' && ctx.can('policy:approve') && b.proposed_by !== ctx.session.user.id && <button className="secondary" disabled={busy} onClick={() => run(() => api(`${ctx.base}/lifecycle/baselines/${b.id}/decision`, 'POST', { decision: 'APPROVE' }, ctx.session.csrf_token))}>Approve</button>}</td></tr>)}</tbody></table></div>}</State>
    {ctx.can('policy:propose') && <form className="pad" onSubmit={e => { e.preventDefault(); run(() => api(`${ctx.base}/lifecycle/baselines`, 'POST', { department: dept, groups: groups.split(',').map(s => s.trim()).filter(Boolean), justification: why }, ctx.session.csrf_token)); }}>
      <div className="form-grid"><label>Department<input className="text-input" value={dept} onChange={e => setDept(e.target.value)}/></label><label>Groups (external IDs, comma separated)<input className="text-input" value={groups} onChange={e => setGroups(e.target.value)}/></label></div>
      <label>Justification<textarea required minLength={8} value={why} onChange={e => setWhy(e.target.value)}/></label><button className="secondary" disabled={busy}>Propose baseline</button></form>}
    {error && <p className="error" role="alert">{error}</p>}</Panel>;
}

function EventPlan({ ctx, id, workflow }: { ctx: Ctx; id: string; workflow?: string }) {
  const plan = useResource<Envelope<Plan>>(`${ctx.base}/lifecycle/events/${id}/plan`);
  const flow = useResource<Envelope<Workflow>>(workflow ? `${ctx.base}/lifecycle/workflows/${workflow}` : null);
  const [picked, setPicked] = useState<number[]>([]); const [why, setWhy] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const start = async () => { setBusy(true); setError(''); try {
    const r = await api<Envelope<{ id: string }>>(`${ctx.base}/lifecycle/events/${id}/workflow`, 'POST', { actions: picked, justification: why }, ctx.session.csrf_token);
    ctx.navigate('Lifecycle', { event: id, workflow: r.data.id });
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><button className="secondary back" onClick={() => ctx.navigate('Lifecycle')}><ArrowLeft size={15}/>All events</button>
    <State {...plan}>{d => { const p = d.data; return <Panel title={`${label(p.event.kind)} plan · ${p.identity.name}`} meta={`${p.rules_version} · RULE-BASED`}>
      {p.status === 'NO_APPROVED_BASELINE' && <div className="pad"><Warning>No approved baseline for this department; nothing is provisioned automatically.</Warning></div>}
      {p.note && <div className="pad"><Warning>{p.note}</Warning></div>}
      {p.actions.map((a, i) => <div className="finding" key={i}><h3>{a.proposal && !workflow && ctx.can('change:propose') && <input type="checkbox" aria-label={`Select ${a.label}`} checked={picked.includes(i)} onChange={e => setPicked(e.target.checked ? [...picked, i] : picked.filter(x => x !== i))}/>}{a.label}{a.decision && <Tag tone={tone(a.decision)}>{a.decision}</Tag>}{!a.proposal && a.kind !== 'retain' && <Tag>no automatic proposal</Tag>}</h3><p>{a.rationale}</p>{a.evidence_ids.length > 0 && <small className="mono block">Evidence {a.evidence_ids.map(e => e.slice(0, 8)).join(' ')}</small>}</div>)}
      {!workflow && ctx.can('change:propose') && <div className="pad"><label>Workflow justification<textarea minLength={8} value={why} onChange={e => setWhy(e.target.value)}/></label><button className="primary" disabled={busy || picked.length === 0 || why.length < 8} onClick={start}>Create proposals for selected actions</button><small className="block">Each proposal is simulated and submitted; every one still needs independent approval and execution.</small></div>}
      {error && <p className="error" role="alert">{error}</p>}</Panel>; }}</State>
    {workflow && <State {...flow}>{d => <Panel title="Workflow" meta={<Tag tone={d.data.status === 'COMPLETED' ? 'ok' : d.data.status === 'PARTIAL' || d.data.status === 'FAILED' ? 'critical' : 'info'}>{d.data.status}</Tag>}>
      {d.data.status === 'PARTIAL' && <div className="pad"><Warning>Some actions failed. Partial outcomes are explicit; review and resubmit the failed proposals.</Warning></div>}
      <div className="table-scroll"><table><tbody>{d.data.changes.map(c => <tr key={c.id}><td><button className="link" onClick={() => ctx.navigate('Change requests', { change: c.id })}>{c.justification}</button></td><td><Tag tone={statusTone(c.status)}>{c.status}</Tag></td></tr>)}</tbody></table></div>
      <p className="pad"><Check size={14}/> Proposals created from this plan.</p></Panel>}</State>}</>;
}
