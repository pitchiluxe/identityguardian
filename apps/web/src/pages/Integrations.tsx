import { fmt, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Tag } from '../ui';
import { ConnectorRegistry, DevSandbox } from './DevTools';

type Run = { id: string; connector: string; status: string; coverage: string; observed: number; unchanged: number; created: number; updated: number; tombstoned: number; rejected: number; errors: { object: string; reason: string }[]; started_at: string; finished_at: string | null };

export function Integrations(ctx: Ctx) {
  const runs = useResource<Envelope<Run[]>>(`${ctx.base}/sync-runs`);
  return <>
    {ctx.dev ? <><DevSandbox ctx={ctx} onChanged={runs.reload}/><ConnectorRegistry ctx={ctx} onSynced={runs.reload}/></>
      : <Panel title="Identity sources"><p className="empty-text">No identity source connected yet.</p></Panel>}
    <State {...runs} empty="No sync runs yet.">{d => <Panel title="Sync history" meta="Latest 20">{d.data.length === 0 ? <p className="empty-text">No sync has run in this environment.</p> : <div className="table-scroll"><table><thead><tr><th>Finished</th><th>Status</th><th>Coverage</th><th>Observed</th><th>Created</th><th>Unchanged</th><th>Closed</th><th>Rejected</th></tr></thead><tbody>
      {d.data.map(r => <tr key={r.id}><td>{fmt(r.finished_at)}</td><td><Tag tone={r.status === 'SUCCEEDED' ? 'ok' : r.status === 'PARTIAL' ? 'warn' : 'critical'}>{r.status}</Tag></td><td>{r.coverage === 'complete_authoritative' ? 'Complete (authoritative)' : 'Partial'}</td><td>{r.observed}</td><td>{r.created}</td><td>{r.unchanged}</td><td>{r.tombstoned}</td><td>{r.rejected}{r.errors.length > 0 && <details><summary>Reasons</summary>{r.errors.map(e => <small className="block" key={e.object}>{e.object}: {e.reason}</small>)}</details>}</td></tr>)}
    </tbody></table></div>}</Panel>}</State></>;
}
