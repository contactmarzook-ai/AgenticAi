import { useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

export function cx(...classes) {
  return classes.filter(Boolean).join(' ');
}

const BUTTON = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300',
  secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:text-gray-400',
  danger: 'bg-white text-red-600 border border-red-200 hover:bg-red-50 disabled:text-red-300',
  ghost: 'text-gray-600 hover:bg-gray-100 disabled:text-gray-300',
};

export function Button({ variant = 'primary', loading, className, children, icon: Icon, ...props }) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed',
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
      <span className="mb-1 block text-xs font-medium text-gray-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-400">{hint}</span>}
    </label>
  );
}

const INPUT = 'w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50';

export function Input(props) {
  return <input {...props} className={cx(INPUT, props.className)} />;
}

export function Textarea(props) {
  return <textarea {...props} className={cx(INPUT, 'font-mono', props.className)} />;
}

export function Select({ children, ...props }) {
  return (
    <select {...props} className={cx(INPUT, 'bg-white', props.className)}>
      {children}
    </select>
  );
}

export function Checkbox({ label, ...props }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-indigo-600" {...props} />
      {label}
    </label>
  );
}

const BADGE = {
  gray: 'bg-gray-100 text-gray-700',
  green: 'bg-green-100 text-green-800',
  red: 'bg-red-100 text-red-800',
  yellow: 'bg-yellow-100 text-yellow-800',
  blue: 'bg-blue-100 text-blue-800',
  indigo: 'bg-indigo-100 text-indigo-800',
};

export function Badge({ color = 'gray', children }) {
  return <span className={cx('inline-block rounded px-1.5 py-0.5 text-xs font-medium', BADGE[color])}>{children}</span>;
}

export function StatusBadge({ status }) {
  const color = { succeeded: 'green', success: 'green', active: 'green', failed: 'red', failure: 'red', denied: 'red', running: 'blue', queued: 'yellow', draft: 'yellow', archived: 'gray' }[status] || 'gray';
  return <Badge color={color}>{status}</Badge>;
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={onClose}>
      <div
        className={cx('flex max-h-[90vh] w-full flex-col rounded-lg bg-white shadow-xl', wide ? 'max-w-4xl' : 'max-w-xl')}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={title}
      >
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100" aria-label="Close">
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
    <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-white px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
      </div>
      <div className="flex gap-2">{actions}</div>
    </div>
  );
}

export function Alert({ kind = 'error', children }) {
  if (!children) return null;
  const style = kind === 'error' ? 'border-red-200 bg-red-50 text-red-700' : kind === 'success' ? 'border-green-200 bg-green-50 text-green-700' : 'border-blue-200 bg-blue-50 text-blue-700';
  return <div className={cx('rounded-md border px-3 py-2 text-sm', style)}>{children}</div>;
}

export function Empty({ children }) {
  return <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">{children}</div>;
}

export function Table({ columns, rows, onRowClick, empty = 'Nothing here yet.' }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row, i) => (
            <tr key={row.id ?? i} onClick={onRowClick ? () => onRowClick(row) : undefined} className={onRowClick ? 'cursor-pointer hover:bg-gray-50' : ''}>
              {columns.map((c) => (
                <td key={c.key} className={cx('px-3 py-2 align-top text-gray-700', c.className)}>
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
    <pre className="max-h-80 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{JSON.stringify(value, null, 2)}</pre>
  );
}
