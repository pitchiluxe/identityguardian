import { useState } from 'react';
import { Check, Download, FileText } from 'lucide-react';
import { api, fmt, useResource } from '../api';
import type { Ctx, Envelope } from '../api';
import { Panel, State, Tag, Warning } from '../ui';

type Report = { id: string; report_type: string; format: string; redaction: string; created_at: string; expires_at: string; row_count: number; digest: string; downloads: number; status: string; created_by_name: string; snapshot: { graph_version: string; notes: string[] } };

export function Reports(ctx: Ctx) {
  const data = useResource<Envelope<{ types: Record<string, string>; reports: Report[] }>>(`${ctx.base}/reports`);
  const [type, setType] = useState('privilege_creep'); const [format, setFormat] = useState('csv'); const [redaction, setRedaction] = useState('standard'); const [hours, setHours] = useState(24);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const generate = async () => { setBusy(true); setError(''); setNotice(''); try {
    const r = await api<Envelope<Report>>(`${ctx.base}/reports`, 'POST', { report_type: type, format, redaction, expires_hours: hours }, ctx.session.csrf_token);
    setNotice(`Report generated: ${r.data.row_count} rows, expires ${fmt(r.data.expires_at)}.`); data.reload();
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <><Warning>Exports cite evidence IDs and the snapshot they were built from. Standard redaction masks addresses and free text; spreadsheet formulas are neutralised; files expire and their content is purged.</Warning>
    {ctx.can('report:create') && <Panel title="Generate a report" meta="Scoped to this environment">
      <div className="pad"><div className="form-grid"><label>Report<select aria-label="Report type" value={type} onChange={e => setType(e.target.value)}>{Object.entries(data.data?.data.types || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Format<select value={format} onChange={e => setFormat(e.target.value)}><option value="csv">CSV</option><option value="json">JSON</option></select></label>
        <label>Redaction<select aria-label="Redaction" value={redaction} onChange={e => setRedaction(e.target.value)}><option value="standard">Standard (masked)</option>{ctx.can('audit:read') && <option value="full">Full (audit authority)</option>}</select></label>
        <label>Expires after (hours)<select value={hours} onChange={e => setHours(Number(e.target.value))}>{[1, 24, 72, 168].map(h => <option key={h}>{h}</option>)}</select></label></div>
        <button className="primary" disabled={busy} onClick={generate}><FileText size={15}/>Generate</button>
        {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status"><Check size={16}/>{notice}</p>}</div></Panel>}
    <State {...data}>{d => <Panel title="Report artifacts" meta={`${d.data.reports.length}`}>{d.data.reports.length === 0 ? <p className="empty-text">No reports yet.</p> : <div className="table-scroll"><table><thead><tr><th>Report</th><th>Rows</th><th>Redaction</th><th>Snapshot</th><th>Expires</th><th>Downloads</th><th></th></tr></thead><tbody>
      {d.data.reports.map(r => <tr key={r.id}><td>{d.data.types[r.report_type]}<small className="block">{r.format.toUpperCase()} · by {r.created_by_name} · {fmt(r.created_at)}</small></td><td>{r.row_count}</td><td><Tag tone={r.redaction === 'full' ? 'warn' : 'neutral'}>{r.redaction}</Tag></td><td className="mono">{r.snapshot.graph_version}</td><td>{fmt(r.expires_at)}</td><td>{r.downloads}</td>
        <td>{r.status === 'EXPIRED' ? <Tag tone="neutral">EXPIRED</Tag> : <a className="secondary" href={`/api/v1${ctx.base}/reports/${r.id}/download`}><Download size={14}/>Download</a>}</td></tr>)}</tbody></table></div>}</Panel>}</State></>;
}
