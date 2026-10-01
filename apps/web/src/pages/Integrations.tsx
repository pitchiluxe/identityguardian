import { useState } from 'react';
import { Check, DatabaseZap, RefreshCw } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Tag, Warning } from '../ui';

type Run = { id: string; connector: string; status: string; coverage: string; observed: number; unchanged: number; created: number; updated: number; tombstoned: number; rejected: number; errors: { object: string; reason: string }[]; started_at: string; finished_at: string | null };

export function Integrations(ctx: Ctx) {
  const runs = useResource<Envelope<Run[]>>(`${ctx.base}/sync-runs`);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [variant, setVariant] = useState('standard');
  const act = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); runs.reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const seed = () => act(async () => { const r = await api<Envelope<{ changed_objects: number }>>(`${ctx.base}/sandbox/seed`, 'POST', { variant, confirm_synthetic: true }, ctx.session.csrf_token); return `Sandbox source updated: ${r.data.changed_objects} SYNTHETIC objects changed. Run a sync to ingest them.`; });
  const sync = (mode: string) => act(async () => { const r = await api<Envelope<Run>>(`${ctx.base}/connectors/sandbox/sync`, 'POST', { mode }, ctx.session.csrf_token); return `Sync ${r.data.status}: ${r.data.observed} observed, ${r.data.created} created, ${r.data.unchanged} unchanged, ${r.data.tombstoned} closed, ${r.data.rejected} rejected.`; });
  return <>
    <Panel title="Contoso sandbox directory" meta={<Tag tone="warn">SYNTHETIC · sandbox connector</Tag>}>
      <div className="pad"><p>The sandbox connector reads a simulated directory/HR source seeded from a deterministic fixture. It never connects to a real identity system. Incremental syncs are partial and never imply that missing objects were deleted; only a full authoritative read closes absent relationships, and those closures are marked inferred.</p>
        {ctx.envKind === 'PRODUCTION' && <Warning>Synthetic data cannot be loaded into a PRODUCTION environment.</Warning>}
        <div className="button-row">
          {ctx.can('sandbox:seed') && <><label className="inline">Fixture<select value={variant} onChange={e => setVariant(e.target.value)}><option value="standard">Standard Contoso</option><option value="alternate_path">Alternate payroll path variant</option></select></label>
            <button className="secondary" disabled={busy} onClick={seed}><DatabaseZap size={15}/>Load synthetic fixture into sandbox source</button></>}
          {ctx.can('connector:sync') && <><button className="primary" disabled={busy} onClick={() => sync('incremental')}><RefreshCw size={15}/>Incremental sync</button><button className="secondary" disabled={busy} onClick={() => sync('full')}>Full authoritative sync</button></>}
          {!ctx.can('connector:sync') && !ctx.can('sandbox:seed') && <p className="muted">Your role can view sync history only.</p>}
        </div></div>
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}
    </Panel>
    <ConnectorRegistry ctx={ctx} onSynced={runs.reload}/>
    <State {...runs} empty="No sync runs yet.">{d => <Panel title="Sync history" meta="Latest 20">{d.data.length === 0 ? <p className="empty-text">No sync has run in this environment.</p> : <div className="table-scroll"><table><thead><tr><th>Finished</th><th>Status</th><th>Coverage</th><th>Observed</th><th>Created</th><th>Unchanged</th><th>Closed</th><th>Rejected</th></tr></thead><tbody>
      {d.data.map(r => <tr key={r.id}><td>{fmt(r.finished_at)}</td><td><Tag tone={r.status === 'SUCCEEDED' ? 'ok' : r.status === 'PARTIAL' ? 'warn' : 'critical'}>{r.status}</Tag></td><td>{r.coverage === 'complete_authoritative' ? 'Complete (authoritative)' : 'Partial'}</td><td>{r.observed}</td><td>{r.created}</td><td>{r.unchanged}</td><td>{r.tombstoned}</td><td>{r.rejected}{r.errors.length > 0 && <details><summary>Reasons</summary>{r.errors.map(e => <small className="block" key={e.object}>{e.object}: {e.reason}</small>)}</details>}</td></tr>)}
    </tbody></table></div>}</Panel>}</State></>;
}

type Connector = { id: string; kind: string; name: string; health: string; authoritative: boolean; has_secret: boolean; config: Record<string, unknown>;
  capabilities: { read: string[]; write: string[]; authoritative_scope: string; page_size: number }; last_run: { status: string; coverage: string; pages: number; retries: number; finished_at: string | null; cursor_token: string | null } | null };

export function ConnectorRegistry({ ctx, onSynced }: { ctx: Ctx; onSynced: () => void }) {
  const list = useResource<Envelope<Connector[]>>(`${ctx.base}/connectors`);
  const [kind, setKind] = useState('mock_entra'); const [authoritative, setAuthoritative] = useState(true);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<string>) => { setBusy(true); setError(''); setNotice(''); try { setNotice(await fn()); list.reload(); onSynced(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const csrf = ctx.session.csrf_token;
  return <Panel title="Connector registry" meta="Mock providers only · real adapters need separate approval">
    <div className="pad"><Warning>Mock Entra ID and Okta connectors replay deterministic SYNTHETIC provider payloads. They never contact a real tenant. Syncs run as worker jobs page by page; a failure keeps a resumable cursor and never implies deletion.</Warning>
      {ctx.can('connector:manage') && ctx.envKind !== 'PRODUCTION' && <div className="button-row"><label className="inline">Provider<select aria-label="Connector provider" value={kind} onChange={e => setKind(e.target.value)}><option value="mock_entra">Mock Entra ID</option><option value="mock_okta">Mock Okta</option></select></label>
        <label className="check"><input type="checkbox" checked={authoritative} onChange={e => setAuthoritative(e.target.checked)}/>Authoritative for its scope</label>
        <button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${ctx.base}/connectors`, 'POST', { kind, name: `${kind === 'mock_entra' ? 'Mock Entra' : 'Mock Okta'} ${new Date().toISOString().slice(11, 19)}`, endpoint: `mock://${kind}/contoso`, authoritative }, csrf); return 'Connector registered.'; })}>Register mock connector</button></div>}
      {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}</div>
    <State {...list}>{d => <div className="table-scroll"><table><thead><tr><th>Connector</th><th>Capabilities</th><th>Health</th><th>Last run</th><th></th></tr></thead><tbody>
      {d.data.map(c => <tr key={c.id}><td><strong>{c.name}</strong><small className="block">{c.kind}{c.authoritative ? ' · authoritative' : ' · non-authoritative'}{c.has_secret ? ' · secret stored (encrypted)' : ''}</small><small className="block">{c.capabilities.authoritative_scope}</small></td>
        <td><small>read {c.capabilities.read.join(', ')}<br/>write {c.capabilities.write.join(', ') || 'none'}</small></td>
        <td><Tag tone={c.health === 'HEALTHY' ? 'ok' : c.health === 'UNKNOWN' ? 'neutral' : 'warn'}>{c.health}</Tag></td>
        <td>{c.last_run ? <small>{c.last_run.status} · {c.last_run.coverage} · {c.last_run.pages} pages · {c.last_run.retries} retries{c.last_run.cursor_token ? ` · resume at ${c.last_run.cursor_token}` : ''}</small> : '—'}</td>
        <td>{c.kind !== 'sandbox' && ctx.can('connector:sync') && <div className="button-row"><button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${ctx.base}/connectors/${c.id}/sync`, 'POST', { mode: 'full' }, csrf); return 'Full sync queued for the worker.'; })}>Queue full sync</button>
          {c.last_run?.status === 'PARTIAL' && <button className="secondary" disabled={busy} onClick={() => run(async () => { await api(`${ctx.base}/connectors/${c.id}/sync`, 'POST', { mode: 'resume' }, csrf); return 'Resume queued from the saved cursor.'; })}>Resume</button>}</div>}</td></tr>)}</tbody></table></div>}</State></Panel>;
}
