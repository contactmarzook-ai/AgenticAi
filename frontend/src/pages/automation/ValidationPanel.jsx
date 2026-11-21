import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, CircleAlert, Loader2 } from 'lucide-react';
import { cx } from '../../lib/ui';
import { nodesMentioned } from './execution';

/** Compact problems indicator that sits on the canvas; expands into a clickable list. */
export default function ValidationPanel({ validation, nodes, onSelectNode }) {
  const [open, setOpen] = useState(false);
  const { status, errors, warnings } = validation;
  if (status === 'idle') return null;
  const total = errors.length + warnings.length;
  const ok = status === 'done' && !total;

  const item = (msg, kind) => {
    const ids = nodesMentioned(msg, nodes);
    const Icon = kind === 'error' ? CircleAlert : AlertTriangle;
    return (
      <li key={`${kind}-${msg}`}>
        <button
          type="button"
          disabled={!ids.length}
          onClick={() => onSelectNode(ids[0])}
          className={cx('flex w-full items-start gap-1.5 rounded px-2 py-1 text-left text-xs', ids.length ? 'hover:bg-brand-50' : 'cursor-default')}
          title={ids.length ? 'Show this step' : undefined}
        >
          <Icon className={cx('mt-0.5 h-3.5 w-3.5 flex-shrink-0', kind === 'error' ? 'text-red-600' : 'text-amber-600')} />
          <span className="text-ink">{msg}</span>
        </button>
      </li>
    );
  };

  return (
    <div data-testid="validation-panel" data-errors={errors.length} data-warnings={warnings.length} className={cx('glass-strong pointer-events-auto max-w-full rounded-lg border shadow-lift', open && total > 0 && 'w-96')}>
      <button
        type="button"
        onClick={() => total && setOpen(!open)}
        className={cx('flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs font-medium', total ? 'cursor-pointer' : 'cursor-default')}
        aria-expanded={open}
      >
        {status === 'checking' && !total ? (
          <><Loader2 className="h-3.5 w-3.5 animate-spin text-muted" /> <span className="text-muted-strong">Checking…</span></>
        ) : status === 'unavailable' ? (
          <span className="text-muted-strong">Could not check the workflow right now</span>
        ) : ok ? (
          <><CheckCircle2 className="h-3.5 w-3.5 text-green-600" /> <span className="text-green-800">No problems found</span></>
        ) : (
          <>
            {errors.length > 0 && (
              <span className="inline-flex items-center gap-1 text-red-700"><CircleAlert className="h-3.5 w-3.5" /> {errors.length} {errors.length === 1 ? 'problem' : 'problems'}</span>
            )}
            {warnings.length > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-800"><AlertTriangle className="h-3.5 w-3.5" /> {warnings.length} {warnings.length === 1 ? 'warning' : 'warnings'}</span>
            )}
            {status === 'checking' && <Loader2 className="h-3 w-3 animate-spin text-muted" />}
            <span className="ml-auto text-muted">{open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}</span>
          </>
        )}
      </button>
      {open && total > 0 && (
        <div className="max-h-64 overflow-y-auto border-t px-1 py-1">
          {errors.length > 0 && <ul>{errors.map((e) => item(e, 'error'))}</ul>}
          {warnings.length > 0 && (
            <>
              <div className="px-2 pb-0.5 pt-1.5 text-[10px] font-semibold uppercase text-amber-800">Warnings</div>
              <ul>{warnings.map((w) => item(w, 'warning'))}</ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
