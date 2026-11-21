import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react';
import api from '../../lib/api';
import { Button, Checkbox, Input, Select, cx } from '../../lib/ui';

// Edits an agent contract. The value IS the JSON Schema document the API stores and validates:
// there is no separate frontend format. Checking happens on the server (POST /agents/check-schema)
// so there is a single validation implementation.

export const TYPES = ['string', 'integer', 'number', 'boolean', 'object', 'array'];
const TYPE_LABEL = { string: 'Text', integer: 'Whole number', number: 'Number', boolean: 'Yes / no', object: 'Group of fields', array: 'List' };

const blankFor = (type) => (type === 'object' ? { type, properties: {}, required: [] } : type === 'array' ? { type, items: { type: 'string' } } : { type });

function retype(node, type) {
  const next = { ...blankFor(type) };
  if (node.description) next.description = node.description;
  return next;
}

function parseScalar(type, text) {
  if (type === 'integer') return /^-?\d+$/.test(text.trim()) ? Number(text) : undefined;
  if (type === 'number') return text.trim() !== '' && !Number.isNaN(Number(text)) ? Number(text) : undefined;
  return text;
}

/** Text box that keeps what you type and commits a parsed value on blur. */
function CommitInput({ value, onCommit, placeholder, className }) {
  const [text, setText] = useState(value);
  const [seen, setSeen] = useState(value);
  if (value !== seen) {
    // The value changed from outside (e.g. JSON edit or reset): show it.
    setSeen(value);
    setText(value);
  }
  return <Input value={text} placeholder={placeholder} className={className} onChange={(e) => setText(e.target.value)} onBlur={() => onCommit(text)} />;
}

function PropertyRow({ name, node, required, onRename, onChange, onRequired, onRemove, depth }) {
  const [open, setOpen] = useState(depth < 1);
  const scalar = !['object', 'array'].includes(node.type);
  const nested = node.type === 'object' ? node : node.type === 'array' && node.items?.type === 'object' ? node.items : null;
  const setNested = (sub) => (node.type === 'object' ? onChange(sub) : onChange({ ...node, items: sub }));
  return (
    <div className="rounded-md border border-line bg-surface">
      <div className="grid grid-cols-12 items-center gap-2 p-2">
        <div className="col-span-12 flex items-center gap-1 sm:col-span-3">
          {nested ? (
            <button type="button" onClick={() => setOpen(!open)} className="text-muted" aria-label={open ? 'Collapse' : 'Expand'}>
              {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          ) : <span className="w-4" />}
          <CommitInput value={name} placeholder="field_name" className="font-mono text-xs" onCommit={(v) => onRename(v.trim())} />
        </div>
        <div className="col-span-6 sm:col-span-3">
          <Select value={node.type} onChange={(e) => onChange(retype(node, e.target.value))} aria-label="Type">
            {TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
          </Select>
        </div>
        {node.type === 'array' ? (
          <div className="col-span-6 sm:col-span-2">
            <Select value={node.items?.type || 'string'} aria-label="List of" onChange={(e) => onChange({ ...node, items: blankFor(e.target.value) })}>
              {TYPES.filter((t) => t !== 'array').map((t) => <option key={t} value={t}>of {TYPE_LABEL[t].toLowerCase()}</option>)}
            </Select>
          </div>
        ) : <div className="hidden sm:col-span-2 sm:block" />}
        <div className="col-span-12 sm:col-span-3">
          <CommitInput value={node.description || ''} placeholder="Description (helps the AI and people)" onCommit={(v) => onChange({ ...node, description: v || undefined })} />
        </div>
        <div className="col-span-12 flex items-center justify-between gap-2 sm:col-span-1 sm:justify-end">
          <Checkbox label="Req." checked={required} onChange={(e) => onRequired(e.target.checked)} />
          <button type="button" onClick={onRemove} className="text-muted hover:text-red-600" aria-label={`Remove ${name}`}>
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
        {scalar && node.type !== 'boolean' && (
          <div className="col-span-12 grid gap-2 sm:col-span-12 sm:grid-cols-2 sm:pl-5">
            <CommitInput
              value={(node.enum || []).join(', ')}
              placeholder="Allowed values (optional, comma separated)"
              onCommit={(v) => {
                const vals = v.split(',').map((s) => s.trim()).filter(Boolean).map((s) => parseScalar(node.type, s));
                const next = { ...node };
                if (vals.length && !vals.includes(undefined)) next.enum = vals;
                else delete next.enum;
                onChange(next);
              }}
            />
            <CommitInput
              value={node.default === undefined ? '' : String(node.default)}
              placeholder="Default value (optional)"
              onCommit={(v) => {
                const next = { ...node };
                const parsed = parseScalar(node.type, v);
                if (v === '' || parsed === undefined) delete next.default;
                else next.default = parsed;
                onChange(next);
              }}
            />
          </div>
        )}
        {node.type === 'boolean' && (
          <div className="col-span-12 sm:pl-5">
            <Select value={node.default === undefined ? '' : String(node.default)} aria-label="Default" onChange={(e) => {
              const next = { ...node };
              if (e.target.value === '') delete next.default;
              else next.default = e.target.value === 'true';
              onChange(next);
            }}>
              <option value="">No default</option>
              <option value="true">Default: yes</option>
              <option value="false">Default: no</option>
            </Select>
          </div>
        )}
      </div>
      {nested && open && (
        <div className="border-t border-line bg-navy-50/60 p-2 pl-6">
          <PropertyList node={nested} onChange={setNested} depth={depth + 1} />
        </div>
      )}
    </div>
  );
}

function PropertyList({ node, onChange, depth = 0 }) {
  const props = node.properties || {};
  const required = node.required || [];
  const entries = Object.entries(props);
  const setProps = (list, req = required) => onChange({ ...node, properties: Object.fromEntries(list), required: req.filter((r) => list.some(([k]) => k === r)) });
  const add = () => {
    let i = entries.length + 1;
    while (props[`field_${i}`]) i += 1;
    setProps([...entries, [`field_${i}`, { type: 'string' }]]);
  };
  return (
    <div className="space-y-2">
      {entries.map(([name, sub], idx) => (
        <PropertyRow
          key={`${idx}-${name}`}
          name={name}
          node={sub}
          depth={depth}
          required={required.includes(name)}
          onRename={(nn) => {
            if (!nn || nn === name || props[nn]) return;
            setProps(entries.map(([k, v]) => (k === name ? [nn, v] : [k, v])), required.map((r) => (r === name ? nn : r)));
          }}
          onChange={(v) => setProps(entries.map(([k, old]) => (k === name ? [k, v] : [k, old])))}
          onRequired={(on) => setProps(entries, on ? [...required, name] : required.filter((r) => r !== name))}
          onRemove={() => setProps(entries.filter(([k]) => k !== name))}
        />
      ))}
      <Button variant="ghost" icon={Plus} onClick={add}>Add field</Button>
    </div>
  );
}

/** Visual + JSON editor for one contract, with the server's verdict underneath. */
export default function SchemaEditor({ value, onChange, defaultSchema, simpleLabel }) {
  const [mode, setMode] = useState('fields');
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [parseError, setParseError] = useState('');
  const [check, setCheck] = useState(null);
  const isDefault = JSON.stringify(value) === JSON.stringify(defaultSchema);

  useEffect(() => {
    const t = setTimeout(() => {
      api.post('/agents/check-schema', { schema: value }).then((r) => setCheck(r.data)).catch(() => setCheck(null));
    }, 400);
    return () => clearTimeout(t);
  }, [value]);

  const switchMode = (m) => {
    if (m === 'json') setText(JSON.stringify(value, null, 2));
    setParseError('');
    setMode(m);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex rounded-md border border-line p-0.5 text-xs">
          {['fields', 'json'].map((m) => (
            <button key={m} type="button" onClick={() => switchMode(m)} className={cx('rounded px-2.5 py-1', mode === m ? 'bg-brand-600 text-white' : 'text-muted-strong hover:bg-brand-50')}>
              {m === 'fields' ? 'Fields' : 'JSON Schema'}
            </button>
          ))}
        </div>
        {!isDefault && (
          <button type="button" className="text-xs text-brand-600 hover:underline" onClick={() => onChange(defaultSchema)}>
            Reset to {simpleLabel}
          </button>
        )}
      </div>
      {mode === 'fields' ? (
        <PropertyList node={value} onChange={onChange} />
      ) : (
        <div>
          <textarea
            rows={12}
            spellCheck={false}
            aria-label="JSON Schema"
            className={cx('w-full rounded-md border px-2.5 py-1.5 font-mono text-xs', parseError ? 'border-red-400' : 'border-line')}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              try {
                onChange(JSON.parse(e.target.value));
                setParseError('');
              } catch (err) {
                setParseError(`Not valid JSON: ${err.message}`);
              }
            }}
          />
          {parseError && <p className="text-xs text-red-600">{parseError}</p>}
        </div>
      )}
      {check && (
        check.valid ? (
          <p className="text-xs text-green-700">✓ Valid contract</p>
        ) : (
          <ul className="list-inside list-disc text-xs text-red-600">{check.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        )
      )}
    </div>
  );
}

/** Form generated from an input schema (used to try an agent). Empty fields are left out so
 *  the server applies defaults; the server does all validation. */
export function SchemaForm({ schema, value, onChange, path = '' }) {
  const props = schema.properties || {};
  const required = schema.required || [];
  const set = (k, v) => {
    const next = { ...(value || {}) };
    if (v === undefined) delete next[k];
    else next[k] = v;
    onChange(next);
  };
  return (
    <div className="space-y-3">
      {Object.entries(props).map(([k, sub]) => {
        const v = value?.[k];
        const label = (
          <span className="mb-1 block text-xs font-medium text-muted-strong">
            {k.replace(/_/g, ' ')}{required.includes(k) ? ' *' : ''}
            {sub.description && <span className="ml-1 font-normal text-muted">— {sub.description}</span>}
          </span>
        );
        let input;
        if (sub.type === 'object') {
          return (
            <fieldset key={k} className="rounded-md border border-line p-3">
              <legend className="px-1 text-xs font-medium text-muted-strong">{k.replace(/_/g, ' ')}{required.includes(k) ? ' *' : ''}</legend>
              <SchemaForm schema={sub} value={v || {}} path={`${path}${k}.`} onChange={(o) => set(k, Object.keys(o).length ? o : undefined)} />
            </fieldset>
          );
        }
        if (sub.enum) {
          input = (
            <Select value={v === undefined ? '' : String(v)} onChange={(e) => set(k, e.target.value === '' ? undefined : sub.enum.find((x) => String(x) === e.target.value))}>
              <option value="">{sub.default !== undefined ? `Default (${sub.default})` : 'Choose…'}</option>
              {sub.enum.map((x) => <option key={String(x)} value={String(x)}>{String(x)}</option>)}
            </Select>
          );
        } else if (sub.type === 'boolean') {
          input = (
            <Select value={v === undefined ? '' : String(v)} onChange={(e) => set(k, e.target.value === '' ? undefined : e.target.value === 'true')}>
              <option value="">{sub.default !== undefined ? `Default (${sub.default ? 'yes' : 'no'})` : 'Not set'}</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </Select>
          );
        } else if (sub.type === 'integer' || sub.type === 'number') {
          input = <Input type="number" step={sub.type === 'integer' ? 1 : 'any'} value={v ?? ''} placeholder={sub.default !== undefined ? `Default: ${sub.default}` : ''} onChange={(e) => set(k, e.target.value === '' ? undefined : Number(e.target.value))} />;
        } else if (sub.type === 'array') {
          input = <ArrayInput value={v} onChange={(x) => set(k, x)} />;
        } else {
          input = <Input value={v ?? ''} placeholder={sub.default !== undefined ? `Default: ${sub.default}` : ''} onChange={(e) => set(k, e.target.value === '' ? undefined : e.target.value)} />;
        }
        return <label key={k} className="block" data-field={`${path}${k}`}>{label}{input}</label>;
      })}
    </div>
  );
}

function ArrayInput({ value, onChange }) {
  const [text, setText] = useState(value === undefined ? '' : JSON.stringify(value));
  return (
    <Input
      className="font-mono text-xs"
      placeholder='JSON list, e.g. ["a", "b"]'
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        if (!e.target.value.trim()) return onChange(undefined);
        try {
          onChange(JSON.parse(e.target.value));
        } catch {
          onChange(e.target.value); // the server reports it as "must be an array"
        }
      }}
    />
  );
}
