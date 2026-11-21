import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../lib/api';
import { Button, PageHeader, Select, Table } from '../lib/ui';

function Stat({ label, value, sub }) {
  return (
    <div className="glass rounded-lg border p-4 shadow-card">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-strong">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-navy">{value}</div>
      {sub && <div className="text-xs text-muted-strong">{sub}</div>}
    </div>
  );
}

export default function Monitoring() {
  const [hours, setHours] = useState(24);
  const [m, setM] = useState(null);

  const load = useCallback(() => api.get('/admin/metrics', { params: { hours } }).then((r) => setM(r.data)), [hours]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Monitoring"
        subtitle="Usage and health of agents and workflows."
        actions={
          <>
            <Select value={hours} onChange={(e) => setHours(Number(e.target.value))} className="w-40">
              <option value={1}>Last hour</option>
              <option value={24}>Last 24 hours</option>
              <option value={168}>Last 7 days</option>
              <option value={720}>Last 30 days</option>
            </Select>
            <Button variant="secondary" icon={RefreshCw} onClick={load}>Refresh</Button>
          </>
        }
      />
      {m && (
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Runs" value={m.runs_total} sub={Object.entries(m.runs_by_source).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none'} />
            <Stat label="Success rate" value={m.success_rate == null ? '—' : `${m.success_rate}%`} sub={`${m.runs_by_status.failed || 0} failed`} />
            <Stat label="Duration" value={`${m.duration_p50_sec}s`} sub={`median · p95 ${m.duration_p95_sec}s`} />
            <Stat label="Tokens" value={(m.prompt_tokens + m.completion_tokens).toLocaleString()} sub={`${m.prompt_tokens.toLocaleString()} prompt · ${m.completion_tokens.toLocaleString()} completion`} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Active users" value={m.inventory.users_active} />
            <Stat label="Active agents" value={m.inventory.agents_active} />
            <Stat label="Active workflows" value={m.inventory.workflows_active} />
            <Stat label="Failed sign-ins" value={m.failed_logins} sub="in this window" />
          </div>
          <section>
            <h2 className="mb-2 font-semibold text-navy">Most used</h2>
            <Table
              rows={m.top_targets.map((t, i) => ({ id: i, ...t }))}
              empty="No runs in this window."
              columns={[
                { key: 'type', label: 'Type' },
                { key: 'name', label: 'Name' },
                { key: 'runs', label: 'Runs' },
                { key: 'failed', label: 'Failed', render: (t) => <span className={t.failed ? 'text-red-600' : ''}>{t.failed}</span> },
              ]}
            />
          </section>
        </div>
      )}
    </div>
  );
}
