import { useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

export function cx(...classes) {
  return classes.filter(Boolean).join(' ');
}

const BUTTON = {
  primary: 'bg-brand-600 text-white shadow-sm hover:bg-brand-700 disabled:bg-brand-300',
  // The one orange call-to-action per screen: dark text on the orange fill (never white).
  accent: 'bg-accent text-navy-900 shadow-sm hover:bg-accent-600 disabled:bg-accent-100 disabled:text-muted-strong',
  secondary: 'bg-surface text-ink border border-line shadow-sm hover:border-brand-200 hover:bg-brand-50 disabled:text-muted',
  danger: 'bg-surface text-red-700 border border-red-200 hover:bg-red-50 disabled:text-red-300',
  ghost: 'text-muted-strong hover:bg-brand-50 hover:text-brand-700 disabled:text-muted/60',
};

export function Button({ variant = 'primary', loading, className, children, icon: Icon, ...props }) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1 disabled:cursor-not-allowed',
        BUTTON[variant],
        className,
      )}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

export function Field({ label, hint, children, className }) {
  return (
    <label className={cx('block', className)}>
      <span className="mb-1 block text-xs font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted-strong">{hint}</span>}
    </label>
  );
}

const INPUT = 'w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/20 disabled:bg-app disabled:text-muted-strong';

export function Input(props) {
  return <input {...props} className={cx(INPUT, props.className)} />;
}

export function Textarea(props) {
  return <textarea {...props} className={cx(INPUT, 'font-mono', props.className)} />;
}

export function Select({ children, ...props }) {
  return (
    <select {...props} className={cx(INPUT, 'bg-surface', props.className)}>
      {children}
    </select>
  );
}

export function Checkbox({ label, ...props }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" className="h-4 w-4 rounded border-line text-brand-600 accent-brand-600 focus:ring-brand-600" {...props} />
      {label}
    </label>
  );
}

const BADGE = {
  // Status colours stay semantic: green ok, red failed, amber queued/draft, blue running, gray disabled.
  gray: 'bg-slate-100 text-slate-700 ring-slate-200',
  green: 'bg-green-50 text-green-800 ring-green-200',
  red: 'bg-red-50 text-red-800 ring-red-200',
  yellow: 'bg-amber-50 text-amber-800 ring-amber-200',
  blue: 'bg-sky-50 text-sky-800 ring-sky-200',
  // Brand tag (not a status).
  indigo: 'bg-brand-50 text-brand-700 ring-brand-200',
};

export function Badge({ color = 'gray', children }) {
  return <span className={cx('inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', BADGE[color])}>{children}</span>;
}

export function StatusBadge({ status }) {
  const color = { succeeded: 'green', success: 'green', active: 'green', live: 'green', failed: 'red', failure: 'red', denied: 'red', off: 'red', running: 'blue', queued: 'yellow', draft: 'yellow', archived: 'gray', 'old version': 'gray', error_continued: 'yellow', skipped: 'gray' }[status] || 'gray';
  return <Badge color={color}>{status}</Badge>;
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/40 p-4" onMouseDown={onClose}>
      <div
        className={cx('flex max-h-[90vh] w-full flex-col rounded-lg border bg-surface shadow-pop', wide ? 'max-w-4xl' : 'max-w-xl')}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={title}
      >
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="text-base font-semibold text-navy">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-brand-50 hover:text-ink" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-surface px-4 py-4 sm:px-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-navy">{title}</h1>
        {subtitle && <p className="text-sm text-muted-strong">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

export function Alert({ kind = 'error', children }) {
  if (!children) return null;
  const style = kind === 'error' ? 'border-red-200 bg-red-50 text-red-700' : kind === 'success' ? 'border-green-200 bg-green-50 text-green-700' : 'border-brand-100 bg-brand-50 text-brand-800';
  return <div className={cx('rounded-md border px-3 py-2 text-sm', style)}>{children}</div>;
}

export function Empty({ children }) {
  return <div className="rounded-lg border border-dashed border-navy-100 bg-surface p-8 text-center text-sm text-muted-strong">{children}</div>;
}

export function Table({ columns, rows, onRowClick, empty = 'Nothing here yet.' }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="overflow-x-auto rounded-lg border bg-surface shadow-card">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="bg-app">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-navy">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, i) => (
            <tr key={row.id ?? i} onClick={onRowClick ? () => onRowClick(row) : undefined} className={onRowClick ? 'cursor-pointer hover:bg-brand-50/70' : ''}>
              {columns.map((c) => (
                <td key={c.key} className={cx('px-4 py-2.5 align-top text-ink', c.className)}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value.endsWith?.('Z') || value.includes?.('+') ? value : value + 'Z');
  return d.toLocaleString();
}

export function JsonBlock({ value }) {
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded bg-navy-900 p-3 text-xs text-navy-50">{JSON.stringify(value, null, 2)}</pre>
  );
}
