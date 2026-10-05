import { useState } from 'react';
import { Check, KeyRound, PlugZap, ShieldAlert } from 'lucide-react';
import { api, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Warning } from '../ui';

type KeyState = { saved: boolean; last4?: string };
type AiSettings = {
  allow_hosted_ai: boolean; can_configure: boolean; provider: 'ollama' | 'anthropic' | 'openai';
  ollama_model: string; anthropic_model: string; openai_model: string; hosted_acknowledged: boolean;
  keys: { anthropic: KeyState; openai: KeyState };
  ollama: { reachable: boolean; model: string; available_models: string[]; installed: boolean };
};
const LABEL = { ollama: 'Ollama (local, default)', anthropic: 'Claude (Anthropic)', openai: 'ChatGPT (OpenAI)' } as const;

export function SettingsPage(ctx: Ctx) {
  const base = `/organizations/${ctx.org}/ai`;
  const res = useResource<Envelope<AiSettings>>(`${base}/settings`);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const [keys, setKeys] = useState({ anthropic: '', openai: '' });
  const [models, setModels] = useState<Partial<Record<'ollama' | 'anthropic' | 'openai', string>>>({});
  const csrf = ctx.session.csrf_token;
  const act = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); res.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <State {...res}>{d => { const s = d.data;
    const model = (p: 'ollama' | 'anthropic' | 'openai') => models[p] ?? s[`${p}_model`];
    const choose = (provider: string) => act(async () => { await api(`${base}/settings`, 'PUT', { provider, ollama_model: model('ollama') || null, anthropic_model: model('anthropic') || null, openai_model: model('openai') || null }, csrf); return `${LABEL[provider as keyof typeof LABEL]} selected.`; });
    const hostedBlocked = (p: 'anthropic' | 'openai') => !s.allow_hosted_ai || !s.keys[p].saved;
    return <>
      <Panel title="AI provider" meta="Used by Investigations and the lab instructor">
        <div className="pad">
          <fieldset className="provider-choice"><legend>Provider</legend>
            {(['ollama', 'anthropic', 'openai'] as const).map(p => <label key={p} className="check">
              <input type="radio" name="provider" checked={s.provider === p} disabled={busy || (p !== 'ollama' && hostedBlocked(p))} onChange={() => choose(p)}/>{LABEL[p]}</label>)}
          </fieldset>
          {!s.allow_hosted_ai && <p className="muted">Hosted AI providers are disabled for this organization</p>}
          <div className="ollama-status"><strong>{s.ollama.reachable ? 'Ollama is running' : 'Ollama is not running'}</strong>
            <p>Ollama runs models on the server machine, so evidence never leaves it. Install Ollama from <a href="https://ollama.com/download" target="_blank" rel="noopener">ollama.com/download</a>, then run <code>ollama pull {model('ollama')}</code>.
              {s.ollama.reachable && !s.ollama.installed && <> The model <code>{model('ollama')}</code> is not pulled yet.</>}</p>
            <label className="inline">Ollama model<input className="text-input" aria-label="Ollama model" value={model('ollama')} onChange={e => setModels({ ...models, ollama: e.target.value })}/></label>
            {s.ollama.available_models.length > 0 && <small className="block">Installed: {s.ollama.available_models.join(', ')}</small>}</div>
          <div className="button-row"><button className="secondary" disabled={busy} onClick={() => choose(s.provider)}>Save model choice</button>
            <button className="secondary" disabled={busy} onClick={() => act(async () => { const r = await api<Envelope<{ ok: boolean; reason?: string; model?: string }>>(`${base}/test`, 'POST', {}, csrf); if (!r.data.ok) throw new Error(r.data.reason || 'Connection failed'); return `Connection works (${r.data.model}).`; })}><PlugZap size={15}/>Test connection</button></div>
        </div>
      </Panel>
      <Panel title="API keys" meta="Your keys only · encrypted · never shown again">
        <div className="pad">
          <Warning><span>Claude and ChatGPT receive the evidence needed to answer each question. Use them only if your organization allows it.</span></Warning>
          {(['anthropic', 'openai'] as const).map(p => <div className="key-row" key={p}>
            <h3><KeyRound size={15}/> {LABEL[p]}</h3>
            {s.keys[p].saved ? <p>Key ending ••••{s.keys[p].last4} <button className="link" disabled={busy} onClick={() => act(async () => { await api(`/ai/keys/${p}`, 'DELETE', undefined, csrf); return 'Key removed.'; })}>Remove</button></p> : <p className="muted">No key saved.</p>}
            <div className="button-row"><input className="text-input" type="password" autoComplete="off" aria-label={`${LABEL[p]} API key`} placeholder={s.keys[p].saved ? 'Replace key' : 'Paste API key'} value={keys[p]} onChange={e => setKeys({ ...keys, [p]: e.target.value })}/>
              <button className="secondary" disabled={busy || !keys[p]} onClick={() => act(async () => { await api(`/ai/keys/${p}`, 'PUT', { api_key: keys[p].trim() }, csrf); setKeys({ ...keys, [p]: '' }); return 'Key saved.'; })}>Save key</button></div>
            <label className="inline">{p === 'openai' ? 'Model ID (required)' : 'Model'}<input className="text-input" aria-label={`${LABEL[p]} model`} placeholder={p === 'openai' ? 'Enter the OpenAI model ID' : 'claude-opus-5-5'} value={model(p)} onChange={e => setModels({ ...models, [p]: e.target.value })}/></label>
          </div>)}
          {s.allow_hosted_ai && !s.hosted_acknowledged && <label className="check"><input type="checkbox" disabled={busy} onChange={e => e.target.checked && act(async () => { await api(`${base}/acknowledge-hosted`, 'POST', {}, csrf); return 'Acknowledged.'; })}/>I understand that evidence for my questions is sent to the selected hosted provider.</label>}
        </div>
      </Panel>
      {s.can_configure && <Panel title="Organization policy" meta="Org admin">
        <div className="pad"><label className="check"><input type="checkbox" checked={s.allow_hosted_ai} disabled={busy} onChange={e => act(async () => { await api(`${base}/policy`, 'PUT', { allow_hosted_ai: e.target.checked }, csrf); return e.target.checked ? 'Hosted AI providers allowed.' : 'Hosted AI providers disabled; everyone uses Ollama.'; })}/>Allow hosted AI providers for this organization</label>
          <p className="muted"><ShieldAlert size={14}/> When allowed, members who save a key and confirm may send investigation evidence to Anthropic or OpenAI. Turning this off takes effect immediately.</p></div>
      </Panel>}
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    </>; }}</State>;
}
