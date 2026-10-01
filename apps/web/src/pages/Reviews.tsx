import { useState } from 'react';
import { ArrowLeft, Check } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope, TwinEdge } from '../api';
import { Panel, State, Tag, Warning } from '../ui';
import { Lineage } from './Access';
import type { Path } from './Access';
import { severityTone } from './Radar';

type Campaign = { id: string; name: string; rules: string[]; status: string; due_at: string; created_at: string; items: number; decided: number; assigned_to_me: number; snapshot: { graph_version: string; effective_at: string } };
type EvidenceFinding = { key: string; rule: string; severity: string; title: string; summary: string; usage: { target: string; text: string; state: string }[]; reaches: { target: string; decision: string; privileged: boolean; paths: Path[] }[]; evidence_ids: string[]; peers?: { sample_size: number; holding: number } };
type Item = { id: string; status: string; recommendation: string; recommendation_basis: string; uncertainty: string[]; reviewer_id: string; reviewer_name: string; decision: string | null; decision_justification: string | null; decided_by_name: string | null; decided_at: string | null; change_request_id: string | null; change_status: string | null; version: number; evidence: { grant: TwinEdge & { attributes: Record<string, unknown> }; findings: EvidenceFinding[] } };
type Reviewer = { user_id: string; display_name: string };

export function Reviews(ctx: Ctx) {
  const list = useResource<Envelope<Campaign[]>>(`${ctx.base}/reviews`);
  const open = ctx.params.campaign;
  if (open) return <CampaignView ctx={ctx} id={open}/>;
  return <>{ctx.can('review:manage') && <NewCampaign ctx={ctx} onDone={list.reload}/>}
    <State {...list}>{d => <Panel title="Review campaigns" meta={`${d.data.length}`}>{d.data.length === 0 ? <p className="empty-text">No campaigns yet.</p> : <div className="table-scroll"><table><thead><tr><th>Campaign</th><th>Rules</th><th>Progress</th><th>Assigned to you</th><th>Due</th><th>Snapshot</th></tr></thead><tbody>
      {d.data.map(c => <tr key={c.id}><td><button className="link" onClick={() => ctx.navigate('Access reviews', { campaign: c.id })}>{c.name}</button></td><td>{c.rules.map(label).join(', ')}</td><td>{c.decided} / {c.items}</td><td>{c.assigned_to_me}</td><td>{fmt(c.due_at)}</td><td className="mono">{c.snapshot.graph_version}</td></tr>)}
    </tbody></table></div>}</Panel>}</State></>;
}

function NewCampaign({ ctx, onDone }: { ctx: Ctx; onDone: () => void }) {
  const reviewers = useResource<Envelope<Reviewer[]>>(`/organizations/${ctx.org}/reviewers`);
  const [name, setName] = useState('Retained and leaver access review'); const [reviewer, setReviewer] = useState('');
  const [rules, setRules] = useState<string[]>(['PRIOR_ROLE_RETAINED', 'TERMINATED_WITH_ACCESS']);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(''); setNotice(''); try {
    const r = await api<Envelope<{ item_count: number }>>(`${ctx.base}/reviews`, 'POST', { name, rules, reviewer_id: reviewer }, ctx.session.csrf_token);
    setNotice(`Campaign created with ${r.data.item_count} evidence-backed items.`); onDone();
  } catch (err) { setError((err as Error).message); } finally { setBusy(false); } };
  return <form className="panel proposal" onSubmit={submit}><h2>Start a review campaign</h2><p>Items are generated from current rule-based findings and freeze their evidence snapshot. Reviewers decide; REMOVE creates a change proposal and never revokes access.</p>
    <div className="form-grid"><label>Name<input className="text-input" required minLength={3} value={name} onChange={e => setName(e.target.value)}/></label>
      <label>Reviewer<select required value={reviewer} onChange={e => setReviewer(e.target.value)}><option value="">Choose a reviewer</option>{(reviewers.data?.data || []).filter(r => r.user_id !== ctx.session.user.id).map(r => <option key={r.user_id} value={r.user_id}>{r.display_name}</option>)}</select></label></div>
    <fieldset className="filters"><legend>Finding rules</legend>{['PRIOR_ROLE_RETAINED', 'TERMINATED_WITH_ACCESS', 'DORMANT_PRIVILEGED', 'UNUSED_PRIVILEGED_ENTITLEMENT'].map(r => <label key={r} className="check"><input type="checkbox" checked={rules.includes(r)} onChange={e => setRules(e.target.checked ? [...rules, r] : rules.filter(x => x !== r))}/>{label(r)}</label>)}</fieldset>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    <button className="primary" disabled={busy || rules.length === 0}>Create campaign</button></form>;
}

function CampaignView({ ctx, id }: { ctx: Ctx; id: string }) {
  const data = useResource<Envelope<{ campaign: Campaign; items: Item[] }>>(`${ctx.base}/reviews/${id}`);
  return <><button className="secondary back" onClick={() => ctx.navigate('Access reviews')}><ArrowLeft size={15}/>All campaigns</button>
    <State {...data}>{d => <Panel title={d.data.campaign.name} meta={`Snapshot ${d.data.campaign.snapshot.graph_version} · effective ${fmt(d.data.campaign.snapshot.effective_at)}`}>
      {d.data.items.map(i => <ReviewItem key={i.id} ctx={ctx} campaign={id} item={i} onDone={data.reload}/>)}</Panel>}</State></>;
}

function ReviewItem({ ctx, campaign, item, onDone }: { ctx: Ctx; campaign: string; item: Item; onDone: () => void }) {
  const [decision, setDecision] = useState(item.recommendation === 'REMOVE' ? 'REMOVE' : 'KEEP'); const [why, setWhy] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const grant = item.evidence.grant; const mine = item.reviewer_id === ctx.session.user.id;
  const [isOpen, setOpen] = useState(item.status === 'PENDING' && mine);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setError(''); try {
    await api(`${ctx.base}/reviews/${campaign}/items/${item.id}/decision`, 'POST', { decision, justification: why, expected_version: item.version }, ctx.session.csrf_token); onDone();
  } catch (err) { setError((err as Error).message); } finally { setBusy(false); } };
  return <details className="finding" open={isOpen} onToggle={e => setOpen(e.currentTarget.open)}><summary><h3 style={{ display: 'inline-flex' }}>{item.evidence.findings[0]?.title || label(grant.type)}<Tag tone={item.recommendation === 'REMOVE' ? 'warn' : 'info'}>Recommends {item.recommendation}</Tag><Tag tone={item.status === 'DECIDED' ? 'ok' : 'neutral'}>{item.status}{item.decision ? ` · ${item.decision}` : ''}</Tag></h3></summary>
    <p>Grant under review: <strong>{label(grant.type)}</strong> · origin {fmt(grant.attributes.origin)} · ticket {fmt(grant.attributes.ticket)} · approver {fmt(grant.attributes.approver)} · since {fmt(grant.valid_from)} · justification “{fmt(grant.attributes.justification)}”</p>
    {item.evidence.findings.map(f => <div key={f.key}><small className="block"><Tag tone={severityTone(f.severity)}>{f.severity}</Tag> {f.summary}</small><ul>{f.usage.map((u, i) => <li key={i}>{u.target}: {u.text}</li>)}</ul>{f.reaches.slice(0, 3).map(r => r.paths.slice(0, 1).map((p, j) => <Lineage key={`${r.target}${j}`} path={p}/>))}</div>)}
    {item.uncertainty.length > 0 && <Warning><span><strong>Uncertainty:</strong> {item.uncertainty.join(' · ')}</span></Warning>}
    <small className="block">Basis: {item.recommendation_basis}. Assigned reviewer: {item.reviewer_name}.</small>
    {item.status === 'DECIDED' ? <p>Decided <strong>{item.decision}</strong> by {item.decided_by_name} on {fmt(item.decided_at)}: “{item.decision_justification}”{item.change_request_id && <> · change proposal <button className="link" onClick={() => ctx.navigate('Change requests', { change: item.change_request_id! })}>{item.change_request_id.slice(0, 8)} ({item.change_status})</button></>}</p>
      : mine && ctx.can('review:decide') ? <form onSubmit={submit} className="decision"><div className="form-grid"><label>Decision<select value={decision} onChange={e => setDecision(e.target.value)}><option value="KEEP">KEEP — access remains</option><option value="REMOVE">REMOVE — create a change proposal</option><option value="ESCALATE">ESCALATE — needs more information</option></select></label></div>
        <label>Justification<textarea required minLength={8} value={why} onChange={e => setWhy(e.target.value)} placeholder="Explain the decision with reference to the evidence."/></label>{error && <p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy}>Record decision</button></form>
      : <small className="block muted">Awaiting the assigned reviewer.</small>}</details>;
}
