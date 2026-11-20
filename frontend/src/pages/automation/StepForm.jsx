import { useEffect, useRef, useState } from 'react';
import { Plus, Variable, X } from 'lucide-react';
import api from '../../lib/api';
import { Button, Checkbox, Field, Input, Select, cx } from '../../lib/ui';
import ConnectionEditor from './ConnectionEditor';

/** Keys a step is expected to output, used to offer variables to later steps. */
export function outputKeys(node, catalog) {
  if (!node) return [];
  if (node.type === 'input') return (node.data?.fields || []).map((f) => f.key);
  if (node.type === 'condition') return ['result'];
  if (node.type === 'switch') return ['matched', 'value'];
  if (node.type === 'loop') return ['results', 'count', 'errors'];
  if (node.type !== 'action') return [];
  const cfg = node.data?.config || {};
  if (node.data?.action === 'set_fields') return Object.keys(cfg.fields || {});
  if (node.data?.action === 'ai_extract') return (cfg.fields || []).filter(Boolean);
  const nt = catalog.find((n) => n.key === node.data?.action);
  const hint = nt?.output_hint || '';
  return [...hint.matchAll(/([a-z_]+)/g)].map((m) => m[1]).filter((k) => k !== 'your' && k !== 'field' && k !== 'names');
}

/** All variables available to a node: the start form plus every step that can run before it. */
export function availableVariables(nodeId, nodes, edges, catalog) {
  const parents = new Map();
  edges.forEach((e) => parents.set(e.target, [...(parents.get(e.target) || []), e.source]));
  const seen = new Set();
  const stack = [...(parents.get(nodeId) || [])];
  while (stack.length) {
    const id = stack.pop();
    if (seen.has(id)) continue;
    seen.add(id);
    stack.push(...(parents.get(id) || []));
  }
  const groups = [];
  nodes.forEach((n) => {
    if (!seen.has(n.id)) return;
    const keys = outputKeys(n, catalog);
    const root = n.type === 'input' ? 'input' : n.id;
    if (keys.length || n.type === 'action') {
      groups.push({ label: n.type === 'input' ? 'Start form' : n.data?.label || n.id, vars: keys.map((k) => ({ label: k, value: `{{${root}.${k}}}` })), root });
    }
  });
  return groups;
}

function VariableMenu({ groups, onPick }) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState('');
  if (!groups.length) return null;
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen(!open)} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-indigo-600 hover:bg-indigo-50" title="Insert data from an earlier step">
        <Variable className="h-3.5 w-3.5" /> Insert data
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border bg-white p-2 shadow-lg">
          {groups.map((g) => (
            <div key={g.root} className="mb-2">
              <div className="px-1 text-[11px] font-semibold uppercase text-gray-400">{g.label}</div>
              {g.vars.map((v) => (
                <button key={v.value} type="button" onClick={() => { onPick(v.value); setOpen(false); }} className="block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-gray-100">
                  {v.label}
                </button>
              ))}
              <div className="flex gap-1 px-1 pt-1">
                <input className="w-full rounded border px-1.5 py-0.5 text-xs" placeholder="other field…" value={custom} onChange={(e) => setCustom(e.target.value.replace(/[^\w.-]/g, ''))} />
                <button type="button" className="text-xs text-indigo-600" onClick={() => { if (custom) { onPick(`{{${g.root}.${custom}}}`); setOpen(false); setCustom(''); } }}>
                  add
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Text input / textarea with "Insert data" that inserts a variable at the cursor. */
export function VarText({ value, onChange, groups, multiline, placeholder, rows = 4 }) {
  const ref = useRef(null);
  const insert = (token) => {
    const el = ref.current;
    const text = value ?? '';
    const pos = el && el.selectionStart != null ? el.selectionStart : text.length;
    onChange(text.slice(0, pos) + token + text.slice(pos));
    setTimeout(() => el?.focus(), 0);
  };
  const cls = 'w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500';
  return (
    <div>
      {groups.length > 0 && (
        <div className="mb-1 flex justify-end">
          <VariableMenu groups={groups} onPick={insert} />
        </div>
      )}
      {multiline ? (
        <textarea ref={ref} rows={rows} className={cls} placeholder={placeholder} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input ref={ref} className={cls} placeholder={placeholder} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}

function KeyValueEditor({ value, onChange, groups }) {
  const rows = Object.entries(value || {});
  const update = (idx, k, v) => {
    const next = rows.map(([rk, rv], i) => (i === idx ? [k, v] : [rk, rv]));
    onChange(Object.fromEntries(next.filter(([rk]) => rk !== '')));
  };
  const [newKey, setNewKey] = useState('');
  return (
    <div className="space-y-2">
      {rows.map(([k, v], i) => (
        <div key={i} className="rounded border bg-gray-50 p-2">
          <div className="mb-1 flex items-center gap-1">
            <input className="flex-1 rounded border px-2 py-1 font-mono text-xs" value={k} onChange={(e) => update(i, e.target.value.replace(/\s/g, '_'), v)} />
            <button type="button" onClick={() => onChange(Object.fromEntries(rows.filter((_, j) => j !== i)))} className="p-1 text-gray-400 hover:text-red-600" aria-label="Remove">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <VarText value={typeof v === 'string' ? v : JSON.stringify(v)} groups={groups} onChange={(nv) => update(i, k, nv)} />
        </div>
      ))}
      <div className="flex gap-2">
        <Input placeholder="new name" value={newKey} onChange={(e) => setNewKey(e.target.value.replace(/\s/g, '_'))} />
        <Button variant="secondary" icon={Plus} disabled={!newKey || newKey in (value || {})} onClick={() => { onChange({ ...(value || {}), [newKey]: '' }); setNewKey(''); }}>
          Add
        </Button>
      </div>
    </div>
  );
}

function JsonField({ value, onChange }) {
  const [text, setText] = useState(() => (value == null || value === '' ? '' : typeof value === 'string' ? value : JSON.stringify(value, null, 2)));
  const [bad, setBad] = useState(false);
  return (
    <div>
      <textarea
        rows={5}
        className={cx('w-full rounded-md border px-2.5 py-1.5 font-mono text-xs', bad ? 'border-red-400' : 'border-gray-300')}
        value={text}
        placeholder='{"name": "{{input.name}}"}'
        onChange={(e) => {
          setText(e.target.value);
          if (!e.target.value.trim()) {
            setBad(false);
            onChange('');
            return;
          }
          try {
            onChange(JSON.parse(e.target.value));
            setBad(false);
          } catch {
            setBad(true);
            onChange(e.target.value);
          }
        }}
      />
      {bad && <p className="text-xs text-red-600">Not valid JSON yet - it will be sent as plain text.</p>}
    </div>
  );
}

function CredentialSelect({ value, onChange, credentialType, credentialTypes }) {
  const [creds, setCreds] = useState([]);
  const [adding, setAdding] = useState(false);
  const types = (credentialType || '').split('|');
  const load = () => api.get('/credentials', { params: { type: credentialType } }).then((r) => setCreds(r.data)).catch(() => {});
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credentialType]);
  return (
    <div className="flex gap-2">
      <Select value={value || ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}>
        <option value="">{creds.length ? 'Choose a connection…' : 'No connections yet'}</option>
        {value && !creds.some((c) => c.id === Number(value)) && <option value={value}>Set by the owner (not shared with you)</option>}
        {creds.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </Select>
      <Button variant="secondary" icon={Plus} onClick={() => setAdding(true)} title="New connection" aria-label="New connection" />
      {adding && (
        <ConnectionEditor
          types={credentialTypes.filter((t) => types.includes(t.key))}
          onClose={() => setAdding(false)}
          onSaved={(c) => {
            setAdding(false);
            load();
            onChange(c.id);
          }}
        />
      )}
    </div>
  );
}

/** Renders the form for one catalog step type. */
export default function StepForm({ nodeType, config, onChange, groups, agents, credentialTypes }) {
  const set = (k, v) => onChange({ ...config, [k]: v });
  return (
    <div className="space-y-3">
      {nodeType.fields.map((f) => {
        const value = config[f.key] ?? f.default ?? '';
        const label = `${f.label}${f.required ? ' *' : ''}`;
        let input;
        switch (f.type) {
          case 'textarea':
            input = <VarText multiline value={value} groups={groups} placeholder={f.placeholder} onChange={(v) => set(f.key, v)} />;
            break;
          case 'boolean':
            input = <Checkbox label={f.help || f.label} checked={!!value} onChange={(e) => set(f.key, e.target.checked)} />;
            break;
          case 'select':
            input = (
              <Select value={value} onChange={(e) => set(f.key, e.target.value)}>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </Select>
            );
            break;
          case 'credential':
            input = <CredentialSelect value={value} credentialType={f.credential_type} credentialTypes={credentialTypes} onChange={(v) => set(f.key, v)} />;
            break;
          case 'agent':
            input = (
              <Select value={value} onChange={(e) => set(f.key, e.target.value ? Number(e.target.value) : '')}>
                <option value="">Choose an agent…</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </Select>
            );
            break;
          case 'json':
            input = <JsonField value={value} onChange={(v) => set(f.key, v)} />;
            break;
          case 'keyvalue':
            input = <KeyValueEditor value={value || {}} groups={groups} onChange={(v) => set(f.key, v)} />;
            break;
          case 'list':
            input = (
              <textarea
                rows={4}
                className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                placeholder="one per line"
                value={Array.isArray(value) ? value.join('\n') : value}
                onChange={(e) => set(f.key, e.target.value.split('\n'))}
                onBlur={(e) => set(f.key, e.target.value.split('\n').map((s) => s.trim()).filter(Boolean))}
              />
            );
            break;
          default:
            input = <VarText value={value === null ? '' : String(value)} groups={groups} placeholder={f.placeholder} onChange={(v) => set(f.key, v)} />;
        }
        return (
          <Field key={f.key} label={f.type === 'boolean' ? '' : label} hint={f.type === 'boolean' ? '' : f.help}>
            {input}
          </Field>
        );
      })}
    </div>
  );
}
