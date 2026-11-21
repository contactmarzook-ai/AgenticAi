import { useCallback, useEffect, useState } from 'react';
import api from '../lib/api';
import { Button, Input, JsonBlock, Modal, PageHeader, Select, StatusBadge, Table, formatDate } from '../lib/ui';

const PAGE = 50;

export default function Audit() {
  const [filters, setFilters] = useState({ action: '', user_email: '', status: '' });
  const [applied, setApplied] = useState(filters);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [detail, setDetail] = useState(null);

  const load = useCallback(() => {
    const params = { limit: PAGE, offset };
    Object.entries(applied).forEach(([k, v]) => v && (params[k] = v));
    api.get('/admin/audit', { params }).then((r) => setData(r.data));
  }, [applied, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const apply = (e) => {
    e.preventDefault();
    setOffset(0);
    setApplied(filters);
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Audit log" subtitle="Sign-ins, configuration changes, runs and denied attempts. Rows cannot be edited or deleted from the app." />
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        <form onSubmit={apply} className="flex flex-wrap gap-2">
          <Input className="w-48" placeholder="action prefix, e.g. agent." value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} />
          <Input className="w-56" placeholder="user email contains" value={filters.user_email} onChange={(e) => setFilters({ ...filters, user_email: e.target.value })} />
          <Select className="w-36" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">Any status</option>
            <option>success</option>
            <option>failure</option>
            <option>denied</option>
          </Select>
          <Button type="submit" variant="secondary">Filter</Button>
        </form>
        <Table
          rows={data.items}
          onRowClick={setDetail}
          columns={[
            { key: 'created_at', label: 'Time', render: (r) => formatDate(r.created_at) },
            { key: 'user_email', label: 'User', render: (r) => r.user_email || '—' },
            { key: 'action', label: 'Action', className: 'font-mono text-xs' },
            { key: 'resource', label: 'Resource', render: (r) => (r.resource_type ? `${r.resource_type} ${r.resource_id ?? ''}` : '—') },
            { key: 'status', label: 'Result', render: (r) => <StatusBadge status={r.status} /> },
            { key: 'ip_address', label: 'IP' },
          ]}
        />
        <div className="flex items-center justify-between text-sm text-muted-strong">
          <span>{data.total ? `${offset + 1}–${Math.min(offset + PAGE, data.total)} of ${data.total}` : ''}</span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
            <Button variant="secondary" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
          </div>
        </div>
      </div>
      {detail && (
        <Modal title={`${detail.action} · ${formatDate(detail.created_at)}`} onClose={() => setDetail(null)}>
          <JsonBlock value={detail} />
        </Modal>
      )}
    </div>
  );
}
