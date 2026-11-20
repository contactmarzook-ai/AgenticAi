import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Badge, Button, JsonBlock, Modal, PageHeader, Select, StatusBadge, Table, formatDate } from '../lib/ui';
import RunSteps from './RunSteps';

const PAGE = 50;

export default function Runs({ user }) {
  const [filters, setFilters] = useState({ status: '', target_type: '', source: '' });
  const [data, setData] = useState({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState(null);

  const load = useCallback(() => {
    const params = { limit: PAGE, offset };
    Object.entries(filters).forEach(([k, v]) => v && (params[k] = v));
    api.get('/runs', { params }).then((r) => setData(r.data));
  }, [filters, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const setFilter = (k, v) => {
    setOffset(0);
    setFilters((f) => ({ ...f, [k]: v }));
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Runs"
        subtitle={can(user, 'run:read_all') ? 'Every agent and workflow execution across the platform.' : 'Your agent and workflow executions.'}
        actions={
          <Button variant="secondary" icon={RefreshCw} onClick={load}>
            Refresh
          </Button>
        }
      />
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        <div className="flex flex-wrap gap-2">
          <Select className="w-40" value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">Any status</option>
            {['queued', 'running', 'succeeded', 'failed'].map((s) => <option key={s}>{s}</option>)}
          </Select>
          <Select className="w-40" value={filters.target_type} onChange={(e) => setFilter('target_type', e.target.value)}>
            <option value="">Agents & workflows</option>
            <option value="agent">Agents</option>
            <option value="workflow">Workflows</option>
          </Select>
          <Select className="w-40" value={filters.source} onChange={(e) => setFilter('source', e.target.value)}>
            <option value="">Any source</option>
            {['chat', 'api', 'test', 'schedule', 'webhook'].map((s) => <option key={s}>{s}</option>)}
          </Select>
        </div>
        <Table
          rows={data.items}
          onRowClick={(r) => api.get(`/runs/${r.id}`).then((res) => setDetail(res.data))}
          empty="No runs match."
          columns={[
            { key: 'id', label: '#' },
            { key: 'created_at', label: 'Started', render: (r) => formatDate(r.created_at) },
            { key: 'target', label: 'Target', render: (r) => <><Badge>{r.target_type}</Badge> {r.target_name}</> },
            { key: 'source', label: 'Source' },
            { key: 'status', label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
            { key: 'tokens', label: 'Tokens', render: (r) => r.prompt_tokens + r.completion_tokens },
            { key: 'error', label: 'Error', className: 'max-w-xs truncate text-red-600', render: (r) => r.error || '' },
          ]}
        />
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>
            {data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} of ${data.total}` : ''}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
            <Button variant="secondary" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
          </div>
        </div>
      </div>
      {detail && (
        <Modal wide title={`Run #${detail.id} · ${detail.target_type} “${detail.target_name}”`} onClose={() => setDetail(null)}>
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-3 text-gray-600">
              <StatusBadge status={detail.status} />
              <span>source: {detail.source}</span>
              {detail.model_name && <span>model: {detail.model_name}</span>}
              <span>{detail.llm_calls} LLM calls</span>
              <span>{detail.prompt_tokens} prompt + {detail.completion_tokens} completion tokens</span>
              <span>{formatDate(detail.started_at)} → {formatDate(detail.finished_at)}</span>
            </div>
            {detail.error && <Alert>{detail.error}</Alert>}
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-gray-500">Input</div>
                <JsonBlock value={detail.input} />
              </div>
              <div>
                <div className="mb-1 text-xs text-gray-500">Output</div>
                <JsonBlock value={detail.output} />
              </div>
            </div>
            <RunSteps steps={detail.steps} />
          </div>
        </Modal>
      )}
    </div>
  );
}
