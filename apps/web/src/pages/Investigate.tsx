import { useState } from 'react';
import { Search, Sparkles } from 'lucide-react';
import { api, fmt, label, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Tag, Warning } from '../ui';

type Fact = { id: string; text: string; evidence_ids: string[] };
type Claim = { text: string; type: string; citations: string[]; evidence_ids: string[] };
type Result = { question: string; status: string; intent: { name: string; params: Record<string, string> } | null; clarification?: string; supported_intents?: Record<string, string>;
  bundle: { facts: Fact[]; complete: boolean; notes: string[] } | null; claims: Claim[]; rejected: { claim: Claim | null; reason: string }[]; model: string | null; model_version: string | null; latency_ms: number | null; note?: string; disclosure?: string };
const DEV_EXAMPLES = ['Why does Erick have access to payroll?', 'Who can access payroll?', 'What exposure paths start from Erick?', 'Show ownerless service accounts', 'Any dormant admins?', 'Does Erick keep access from his previous role?']; // dev only: fixture personas
const EXAMPLES = ['Who can access payroll?', 'Show ownerless service accounts', 'Any dormant admins?', 'Which identities have privileged access?'];
const tone = (s: string) => s === 'VALIDATED' ? 'ok' : s === 'PARTIAL' || s === 'FALLBACK' ? 'warn' : s === 'AI_UNAVAILABLE' || s === 'INSUFFICIENT' ? 'critical' : 'info';

export function Investigate(ctx: Ctx) {
  const [question, setQuestion] = useState(''); const [useModel, setUseModel] = useState(true);
  const [result, setResult] = useState<Result | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const history = useResource<Envelope<{ id: string; question: string; status: string; created_at: string; model: string | null }[]>>(`${ctx.base}/investigations`);
  const ask = async (q: string) => { setBusy(true); setError(''); setQuestion(q); try {
    setResult((await api<Envelope<Result>>(`${ctx.base}/investigations/query`, 'POST', { question: q, use_model: useModel }, ctx.session.csrf_token)).data); history.reload();
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><Warning>Read-only and advisory. Answers come from deterministic queries over evidence you are authorized to see; the local model only explains cited facts and cannot change access.</Warning>
    <form className="panel pad" onSubmit={e => { e.preventDefault(); ask(question); }}><label>Question<input className="text-input" aria-label="Investigation question" maxLength={500} value={question} onChange={e => setQuestion(e.target.value)} placeholder={ctx.dev ? 'Why does Erick have access to payroll?' : 'Who can access payroll?'}/></label>
      <div className="button-row"><button className="primary" disabled={busy || question.length < 4}><Search size={15}/>{busy ? 'Investigating…' : 'Investigate'}</button><label className="check"><input type="checkbox" checked={useModel} onChange={e => setUseModel(e.target.checked)}/>Ask the local model to explain the evidence</label></div>
      <div className="button-row">{(ctx.dev ? DEV_EXAMPLES : EXAMPLES).map(x => <button type="button" key={x} className="link" onClick={() => ask(x)}>{x}</button>)}</div>{error && <p className="error" role="alert">{error}</p>}</form>
    {result && <Panel title={result.question} meta={<Tag tone={tone(result.status)}>{result.status}</Tag>}>
      {result.status === 'CLARIFICATION' ? <div className="pad"><p>{result.clarification}</p><ul>{Object.entries(result.supported_intents || {}).map(([k, v]) => <li key={k}><strong>{label(k)}</strong>: {v}</li>)}</ul></div> : <>
        <div className="pad"><small className="block">Intent {result.intent && label(result.intent.name)} · {result.model ? `model ${result.model} (${result.model_version || 'version unknown'}), ${result.latency_ms} ms` : 'no model used'}{result.note ? ` · ${result.note}` : ''}</small>
          {result.bundle && !result.bundle.complete && <Warning>Evidence is partial: {result.bundle.notes.join(' ')}</Warning>}
          <h3><Sparkles size={15}/> Answer</h3>{result.claims.length === 0 ? <p>Insufficient evidence to answer.</p> : result.claims.map((c, i) => <div key={i} className={`claim ${c.type}`}><Tag>{c.type}</Tag> {c.text} <small className="mono">[{c.citations.join(', ')}]</small></div>)}
          {result.rejected.length > 0 && <details><summary>{result.rejected.length} model claim(s) rejected by validation</summary><ul>{result.rejected.map((r, i) => <li key={i}>{r.claim?.text || '(malformed)'} — <em>{r.reason}</em></li>)}</ul></details>}
          <h3>Evidence bundle</h3><ol className="facts">{(result.bundle?.facts || []).map(f => <li key={f.id}><strong>{f.id}</strong> {f.text} {f.evidence_ids.length > 0 && <small className="mono">evidence {f.evidence_ids.slice(0, 4).map(e => e.slice(0, 8)).join(' ')}{f.evidence_ids.length > 4 ? '…' : ''}</small>}</li>)}</ol>
          <small className="block">{result.disclosure}</small></div></>}</Panel>}
    <State {...history}>{d => d.data.length > 0 ? <Panel title="Your recent investigations" meta="Latest 20">{d.data.map(h => <div className="history-row" key={h.id}><button className="link" onClick={() => ask(h.question)}>{h.question}</button><small>{fmt(h.created_at)} · {h.status}{h.model ? ` · ${h.model}` : ''}</small></div>)}</Panel> : null}</State></>;
}
