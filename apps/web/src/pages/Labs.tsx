import { useState } from 'react';
import { ArrowLeft, Check, GraduationCap, Lightbulb, RotateCcw, Sparkles } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { KV, Panel, State, Tag, Warning } from '../ui';

type LabInfo = { id: string; title: string; objective: string; tasks: string[] };
type Attempt = { id: string; lab_id: string; status: string; started_at: string; environment_id: string; learner: string; score: { total: number; passed: boolean } | null };
type Report = { lab: { title: string; version: string }; score: { total: number; passed: boolean; pass_mark: number; breakdown: Record<string, number>; safety_failures: { rule: string; message: string }[] };
  checks: { id: string; category: string; passed: boolean; text: string }[]; misconceptions: string[]; changes: Record<string, unknown>[]; hints_used: { level: number }[]; resets: number; rubric: string; graded_by: string };
const TEMPLATES: Record<string, object> = {
  add_membership: { type: 'add_membership', identity: 'idn-', group: 'grp-', justification: '' }, remove_membership: { type: 'remove_membership', identity: 'idn-', group: 'grp-' },
  assign_role: { type: 'assign_role', identity: 'idn-', role: 'role-' }, create_role: { type: 'create_role', role: 'role-lab-', name: '', permissions: ['perm-'] },
  set_identity: { type: 'set_identity', identity: 'idn-', attributes: { department: '', manager: 'idn-' } }, register_mfa: { type: 'register_mfa', identity: 'idn-', method: 'webauthn' },
  reset_password: { type: 'reset_password', identity: 'idn-', verification: 'manager_callback', justification: '' }, unlock_account: { type: 'unlock_account', identity: 'idn-' },
  disable_account: { type: 'disable_account', identity: 'idn-' }, set_owner: { type: 'set_owner', machine: 'idn-', owner: 'idn-' }, rotate_credential: { type: 'rotate_credential', credential: '' },
  add_condition: { type: 'add_condition', relationship: '', condition: 'mfa_required' }, configure_sso: { type: 'configure_sso', application: 'app-', issuer: '', audience: '', mappings: {} },
  answer: { type: 'answer', question: '', value: '' },
};

export function Labs(ctx: Ctx) {
  const catalog = useResource<Envelope<{ version: string; labs: LabInfo[] }>>(`/organizations/${ctx.org}/labs`);
  const attempts = useResource<Envelope<Attempt[]>>(`/organizations/${ctx.org}/labs/attempts`);
  const [error, setError] = useState('');
  if (ctx.params.attempt) return <AttemptView ctx={ctx} id={ctx.params.attempt}/>;
  const start = async (lab: string) => { setError(''); try {
    const r = await api<Envelope<{ id: string }>>(`/organizations/${ctx.org}/labs/${lab}/attempts`, 'POST', {}, ctx.session.csrf_token);
    ctx.navigate('Labs', { attempt: r.data.id });
  } catch (e) { setError((e as Error).message); } };
  return <><Warning>Each attempt clones the SYNTHETIC Contoso scenario into a LAB environment only you can see. Lab actions never reach any other environment. Scores come from deterministic validators.</Warning>
    {error && <p className="error" role="alert">{error}</p>}
    <State {...attempts}>{d => d.data.length === 0 ? null : <Panel title="Your attempts" meta={`${d.data.length}`}><div className="table-scroll"><table><thead><tr><th>Lab</th><th>Status</th><th>Score</th><th>Started</th></tr></thead><tbody>{d.data.map(a => <tr key={a.id}><td><button className="link" onClick={() => ctx.navigate('Labs', { attempt: a.id })}>{label(a.lab_id)}</button>{a.learner && ctx.can('lab:manage') ? <small className="block">{a.learner}</small> : null}</td><td><Tag tone={a.status === 'SUBMITTED' ? 'ok' : 'info'}>{a.status}</Tag></td><td>{a.score ? `${a.score.total}${a.score.passed ? ' · passed' : ' · not passed'}` : '—'}</td><td>{fmt(a.started_at)}</td></tr>)}</tbody></table></div></Panel>}</State>
    <State {...catalog}>{d => <Panel title="Lab catalog" meta={d.data.version}><div className="metric-grid pad">{d.data.labs.map(l => <div key={l.id} className="metric"><span><GraduationCap size={14}/> {l.title}</span><p>{l.objective}</p>{ctx.can('lab:attempt') && <button className="secondary" onClick={() => start(l.id)}>Start attempt</button>}</div>)}</div></Panel>}</State></>;
}

function AttemptView({ ctx, id }: { ctx: Ctx; id: string }) {
  const base = `/organizations/${ctx.org}/labs/attempts/${id}`;
  const data = useResource<Envelope<{ attempt: Attempt & { environment_name: string; hints_used: { level: number }[]; resets: number; result: Report | null }; lab: LabInfo; actions: { action: { type: string }; outcome: string; created_at: string }[] }>>(base);
  const [kind, setKind] = useState('add_membership'); const [text, setText] = useState(JSON.stringify(TEMPLATES.add_membership, null, 2));
  const [hint, setHint] = useState<{ level: number; hint: string; kind: string } | null>(null); const [explain, setExplain] = useState<{ source: string; claims?: { text: string; citations: string[] }[]; explanation?: string[]; note?: string } | null>(null);
  const [solution, setSolution] = useState<string[] | null>(null);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<string | void>) => { setBusy(true); setError(''); setNotice(''); try { const m = await fn(); if (m) setNotice(m); data.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const csrf = ctx.session.csrf_token;
  return <><button className="secondary back" onClick={() => ctx.navigate('Labs')}><ArrowLeft size={15}/>All labs</button>
    <State {...data}>{d => { const a = d.data.attempt; const active = a.status === 'ACTIVE'; const nextHint = (a.hints_used?.length || 0) + 1;
      return <><Panel title={d.data.lab.title} meta={<Tag tone={active ? 'info' : 'ok'}>{a.status}</Tag>}>
        <div className="pad"><p>{d.data.lab.objective}</p><ul>{d.data.lab.tasks.map(t => <li key={t}>{t}</li>)}</ul>
          <div className="button-row"><button className="secondary" onClick={() => ctx.selectEnv(a.environment_id)}>Explore this lab environment</button><small>{a.environment_name}</small></div></div></Panel>
        {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
        {active && <Panel title="Act in your lab" meta="Applied to this attempt only">
          <div className="pad"><label className="inline">Action<select aria-label="Lab action type" value={kind} onChange={e => { setKind(e.target.value); setText(JSON.stringify(TEMPLATES[e.target.value], null, 2)); }}>{Object.keys(TEMPLATES).map(k => <option key={k}>{k}</option>)}</select></label>
            <textarea className="code" aria-label="Lab action" rows={7} value={text} onChange={e => setText(e.target.value)}/>
            <div className="button-row"><button className="primary" disabled={busy} onClick={() => run(async () => { let action; try { action = JSON.parse(text); } catch { throw new Error('Action is not valid JSON'); } await api(`${base}/actions`, 'POST', { action }, csrf); return 'Action applied to your lab.'; })}>Apply action</button>
              <button className="secondary" disabled={busy || nextHint > 3} onClick={() => run(async () => { setHint((await api<Envelope<{ level: number; hint: string; kind: string }>>(`${base}/hint?level=${nextHint}`)).data); })}><Lightbulb size={14}/>{nextHint > 3 ? 'All hints used' : `Hint ${nextHint} of 3`}</button>
              <button className="secondary" disabled={busy} onClick={() => run(async () => { setExplain((await api<Envelope<typeof explain>>(`${base}/explain`, 'POST', {}, csrf)).data); })}><Sparkles size={14}/>Ask the instructor</button>
              <button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${base}/reset`, 'POST', {}, csrf); return 'Attempt reset to the scenario baseline.'; })}><RotateCcw size={14}/>Reset attempt</button>
              <button className="primary" disabled={busy} onClick={() => run(async () => { await api(`${base}/submit`, 'POST', {}, csrf); return 'Submitted for deterministic grading.'; })}>Submit for grading</button></div>
            {hint && <div className="claim recommendation"><Tag>Hint {hint.level} · {hint.kind}</Tag> {hint.hint}</div>}
            {explain && <div className="claim inference"><Tag>{explain.source}</Tag> {(explain.claims?.map(c => `${c.text} [${c.citations.join(', ')}]`) || explain.explanation || []).join(' ')} {explain.note && <small className="block">{explain.note}</small>}</div>}</div></Panel>}
        <Panel title="Action log" meta={`${d.data.actions.length} · resets ${a.resets}`}>{d.data.actions.length === 0 ? <p className="empty-text">No actions yet.</p> : d.data.actions.map((x, i) => <div className="history-row" key={i}><strong><Tag tone={x.outcome === 'rejected' ? 'critical' : 'neutral'}>{x.outcome}</Tag> {x.action.type}</strong><small className="mono">{JSON.stringify(x.action)}</small></div>)}</Panel>
        {a.result && <ReportView report={a.result}/>}
        <div className="button-row">{!solution && <button className="link" onClick={() => run(async () => { setSolution((await api<Envelope<{ steps: string[] }>>(`${base}/solution${active ? '?confirm=true' : ''}`)).data.steps); })}>{active ? 'Reveal worked solution (recorded in your report)' : 'View worked solution'}</button>}</div>
        {solution && <Panel title="Worked solution" meta={active ? 'Viewed before submission' : 'After completion'}><ol className="facts">{solution.map(s => <li key={s}>{s}</li>)}</ol></Panel>}</>; }}</State></>;
}

function ReportView({ report }: { report: Report }) {
  return <Panel title="Lab report" meta={<Tag tone={report.score.passed ? 'ok' : 'critical'}>{report.score.passed ? 'PASSED' : 'NOT PASSED'} · {report.score.total}/100</Tag>}>
    <KV rows={[['Correctness (50)', report.score.breakdown.correctness], ['Least privilege (25)', report.score.breakdown.least_privilege], ['Evidence / workflow (25)', report.score.breakdown.evidence], ['Pass mark', report.score.pass_mark], ['Hints used', report.hints_used.length], ['Resets', report.resets], ['Graded by', report.graded_by]]}/>
    {report.score.safety_failures.length > 0 && <div className="pad"><Warning><span><strong>Safety failures (block passing):</strong> {report.score.safety_failures.map(s => s.message).join(' · ')}</span></Warning></div>}
    <ul className="pad">{report.checks.map(c => <li key={c.id}><Tag tone={c.passed ? 'ok' : 'warn'}>{c.passed ? 'PASS' : 'MISS'}</Tag> {c.text} <small>({label(c.category)})</small></li>)}</ul>
    {report.misconceptions.length > 0 && <div className="pad"><h3>Misconceptions</h3><ul>{report.misconceptions.map(m => <li key={m}>{m}</li>)}</ul></div>}
    <small className="pad block">{report.rubric}</small></Panel>;
}
