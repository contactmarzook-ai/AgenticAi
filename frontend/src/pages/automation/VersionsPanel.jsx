import { FolderOpen, Lock, Play } from 'lucide-react';
import { Badge, Button, cx, formatDate } from '../../lib/ui';

function stateOf(v) {
  if (v.status === 'active') return { label: 'live', color: 'green' };
  if (v.status === 'draft') return { label: 'draft', color: 'yellow' };
  return v.published ? { label: 'published earlier', color: 'gray' } : { label: 'archived', color: 'gray' };
}

function RunCounts({ runs }) {
  const ok = runs?.succeeded || 0;
  const failed = runs?.failed || 0;
  const other = Object.entries(runs || {}).filter(([k, n]) => !['succeeded', 'failed'].includes(k) && n > 0);
  if (!ok && !failed && !other.length) return <span>no runs</span>;
  return (
    <span className="inline-flex flex-wrap gap-x-2">
      {ok > 0 && <span className="text-green-700">{ok} succeeded</span>}
      {failed > 0 && <span className="text-red-700">{failed} failed</span>}
      {other.map(([k, n]) => <span key={k}>{n} {k}</span>)}
    </span>
  );
}

/** Every version of the workflow with its state and run counts; open one, or run a published one. */
export default function VersionsPanel({ versions, currentId, canRun, onOpen, onRun }) {
  if (!versions) return <p className="text-sm text-muted-strong">Loading versions…</p>;
  if (!versions.length) return <p className="text-sm text-muted-strong">Save the workflow to create its first version.</p>;
  return (
    <div data-testid="versions-panel" className="space-y-2">
      <h3 className="font-semibold text-navy">Versions</h3>
      <p className="text-xs text-muted-strong">Published versions are read-only: they always run exactly as published. Saving changes to one starts a new draft.</p>
      <ul className="space-y-2">
        {versions.map((v) => {
          const st = stateOf(v);
          const isCurrent = v.id === currentId;
          return (
            <li key={v.id} data-version={v.version} className={cx('rounded-md border p-2.5 text-sm', isCurrent && 'border-brand-300 bg-brand-50/60')}>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">v{v.version}</span>
                <Badge color={st.color}>{st.label}</Badge>
                {v.published && <Lock className="h-3.5 w-3.5 text-muted" aria-label="read-only" />}
                {isCurrent && <span className="ml-auto text-xs font-medium text-brand-700">open here</span>}
              </div>
              <div className="mt-1 space-y-0.5 text-xs text-muted-strong">
                <div>{v.published_at ? `Published ${formatDate(v.published_at)}` : `Last saved ${formatDate(v.updated_at)}`}</div>
                <div><RunCounts runs={v.runs} /></div>
              </div>
              {(!isCurrent || (v.published && canRun)) && (
                <div className="mt-2 flex gap-2">
                  {!isCurrent && <Button variant="secondary" className="!py-1 text-xs" icon={FolderOpen} onClick={() => onOpen(v)}>Open</Button>}
                  {v.published && canRun && <Button variant="secondary" className="!py-1 text-xs" icon={Play} onClick={() => onRun(v)}>Run v{v.version}</Button>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
