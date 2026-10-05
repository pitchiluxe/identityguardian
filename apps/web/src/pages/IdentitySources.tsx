import { useState } from 'react';
import { Check, RefreshCw } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Tag } from '../ui';

type Source = { id: string; kind: string; name: string; health: string; has_secret: boolean; config: Record<string, string>;
  last_run: { status: string; coverage: string; pages: number; finished_at: string | null; cursor_token: string | null } | null };

/** Real identity sources (all modes). Mock connectors live in DevTools and exist only in development. */
export function IdentitySources({ ctx, onSynced }: { ctx: Ctx; onSynced: () => void }) {
  const list = useResource<Envelope<Source[]>>(`${ctx.base}/connectors`);
  const [form, setForm] = useState({ name: 'Entra test tenant', tenant_id: '', client_id: '', client_secret: '' });
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const csrf = ctx.session.csrf_token;
  const run = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); list.reload(); onSynced(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const connect = (event: React.FormEvent) => { event.preventDefault(); run(async () => {
    await api(`${ctx.base}/connectors`, 'POST', { kind: 'entra', ...form }, csrf);
    setForm({ ...form, client_secret: '' });
    return 'Microsoft Entra ID connected. Run a sync to read the tenant.'; }); };
  const allowed = ctx.envKind === 'SANDBOX' || ctx.envKind === 'PRODUCTION';
  const sources = (list.data?.data || []).filter(s => s.kind === 'entra');
  return <Panel title="Identity sources" meta="Read-only · nothing is ever written back">
    <div className="pad">
      {ctx.can('connector:manage') && <form className="proposal" onSubmit={connect}>
        <h3>Connect Microsoft Entra ID (read-only)</h3>
        <p className="muted">Uses an app registration with read-only Microsoft Graph application permissions (User.Read.All, Group.Read.All, Directory.Read.All, Application.Read.All, RoleManagement.Read.Directory). The client secret is encrypted and never shown again.</p>
        {!allowed && <p className="muted">Select a SANDBOX or PRODUCTION environment to connect a tenant (lab environments are training-only). Administrators can create a sandbox in Administration.</p>}
        <div className="form-grid">
          <label>Name<input className="text-input" aria-label="Name" required minLength={3} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label>
          <label>Tenant ID<input className="text-input" aria-label="Tenant ID" required placeholder="Directory (tenant) ID" value={form.tenant_id} onChange={e => setForm({ ...form, tenant_id: e.target.value.trim() })}/></label>
          <label>Client ID<input className="text-input" aria-label="Client ID" required placeholder="Application (client) ID" value={form.client_id} onChange={e => setForm({ ...form, client_id: e.target.value.trim() })}/></label>
          <label>Client secret<input className="text-input" aria-label="Client secret" type="password" autoComplete="off" required value={form.client_secret} onChange={e => setForm({ ...form, client_secret: e.target.value })}/></label>
        </div>
        <button className="primary" disabled={busy || !allowed}>Connect tenant</button>
      </form>}
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    </div>
    <State {...list}>{() => sources.length === 0 ? <p className="empty-text">No identity source connected yet.</p> : <div className="table-scroll"><table><thead><tr><th>Source</th><th>Health</th><th>Last run</th><th></th></tr></thead><tbody>
      {sources.map(s => <tr key={s.id}><td><strong>{s.name}</strong><small className="block">Microsoft Entra ID · tenant {s.config.tenant_id}</small></td>
        <td><Tag tone={s.health === 'HEALTHY' ? 'ok' : s.health === 'UNKNOWN' ? 'neutral' : 'warn'}>{s.health}</Tag></td>
        <td>{s.last_run ? <small>{s.last_run.status} · {s.last_run.coverage} · {s.last_run.pages} pages · {fmt(s.last_run.finished_at)}</small> : '—'}</td>
        <td>{ctx.can('connector:sync') && <div className="button-row"><button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${ctx.base}/connectors/${s.id}/sync`, 'POST', { mode: 'full' }, csrf); return 'Sync queued; the worker reads the tenant page by page.'; })}><RefreshCw size={15}/>Sync now</button>
          {s.last_run?.status === 'PARTIAL' && <button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${ctx.base}/connectors/${s.id}/sync`, 'POST', { mode: 'resume' }, csrf); return 'Resume queued from the saved cursor.'; })}>Resume</button>}</div>}</td></tr>)}
    </tbody></table></div>}</State>
  </Panel>;
}
