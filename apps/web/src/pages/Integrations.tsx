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
    <State {...runs} empty="No sync runs yet.">{d => <Panel title="Sync history" meta="Latest 20">{d.data.length === 0 ? <p className="empty-text">No sync has run in this environment.</p> : <div className="table-scroll"><table><thead><tr><th>Finished</th><th>Status</th><th>Coverage</th><th>Observed</th><th>Created</th><th>Unchanged</th><th>Closed</th><th>Rejected</th></tr></thead><tbody>
      {d.data.map(r => <tr key={r.id}><td>{fmt(r.finished_at)}</td><td><Tag tone={r.status === 'SUCCEEDED' ? 'ok' : r.status === 'PARTIAL' ? 'warn' : 'critical'}>{r.status}</Tag></td><td>{r.coverage === 'complete_authoritative' ? 'Complete (authoritative)' : 'Partial'}</td><td>{r.observed}</td><td>{r.created}</td><td>{r.unchanged}</td><td>{r.tombstoned}</td><td>{r.rejected}{r.errors.length > 0 && <details><summary>Reasons</summary>{r.errors.map(e => <small className="block" key={e.object}>{e.object}: {e.reason}</small>)}</details>}</td></tr>)}
    </tbody></table></div>}</Panel>}</State></>;
}
