import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api, { errorMessage } from '../../lib/api';
import { Alert, StatusBadge, cx, formatDate } from '../../lib/ui';
import { SOURCE_LABELS, durationOf, formatDuration } from './execution';

/** Recent runs of this workflow (every version). Clicking one shows it in the builder. */
export default function RunHistory({ groupId, versionOf, currentId, shownRunId, refreshKey, onOpen }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (!groupId) return;
    api.get('/runs', { params: { group_id: groupId, limit: 20 } })
      .then((r) => { setData(r.data); setError(''); })
      .catch((err) => setError(errorMessage(err)));
  }, [groupId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  if (!groupId) return <p className="text-sm text-muted-strong">Save the workflow to start keeping a history of its runs.</p>;

  return (
    <div data-testid="run-history" className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-navy">Recent runs</h3>
        <button type="button" onClick={load} className="rounded p-1 text-muted-strong hover:bg-brand-50 hover:text-brand-700" title="Refresh" aria-label="Refresh history">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      <Alert>{error}</Alert>
      {data && !data.items.length && <p className="text-sm text-muted-strong">No runs yet. Use <b>Test</b> to try it.</p>}
      {data && data.items.length > 0 && (
        <ul className="divide-y rounded-md border">
          {data.items.map((r) => {
            const v = versionOf(r.target_id);
            const ms = durationOf(r.started_at || r.created_at, r.finished_at);
            return (
              <li key={r.id}>
                <button
                  type="button"
                  data-run-id={r.id}
                  onClick={() => onOpen(r)}
                  className={cx('w-full px-2.5 py-2 text-left hover:bg-brand-50', shownRunId === r.id && 'bg-brand-50')}
                >
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-ink">#{r.id}</span>
                    <StatusBadge status={r.status} />
                    <span className="text-xs text-muted-strong">{SOURCE_LABELS[r.source] || r.source}</span>
                    {v != null && (
                      <span className={cx('ml-auto rounded px-1.5 text-[11px]', r.target_id === currentId ? 'bg-brand-100 text-brand-800' : 'bg-slate-100 text-slate-700')} title={r.target_id === currentId ? 'The version open here' : 'Another version'}>
                        v{v}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex gap-2 text-xs text-muted-strong">
                    <span>{formatDate(r.created_at)}</span>
                    {r.finished_at && ms != null && <span>· {formatDuration(ms)}</span>}
                  </div>
                  {r.error && r.status === 'failed' && <div className="mt-0.5 truncate text-xs text-red-700">{r.error}</div>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {data?.total > data?.items.length && (
        <a className="block text-xs text-brand-600 hover:underline" href={`#/runs?group=${encodeURIComponent(groupId)}`}>See all {data.total} runs in History</a>
      )}
    </div>
  );
}
