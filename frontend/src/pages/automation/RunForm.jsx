import { useState } from 'react';
import { Checkbox, Field, Input, Select, Textarea } from '../../lib/ui';

/** The Start step's form, filled in by whoever runs the automation. Falls back to raw JSON. */
export default function RunForm({ fields, value, onChange }) {
  const [raw, setRaw] = useState(false);
  const [text, setText] = useState(JSON.stringify(value || {}, null, 2));
  const [bad, setBad] = useState(false);
  const set = (k, v) => onChange({ ...value, [k]: v });

  if (raw || !fields?.length) {
    return (
      <div className="space-y-1">
        <Field label="Input (JSON)" hint={!fields?.length ? 'This automation has no form. Send any JSON object (or leave {}).' : undefined}>
          <Textarea
            rows={6}
            value={text}
            className={bad ? 'border-red-400' : ''}
            onChange={(e) => {
              setText(e.target.value);
              try {
                const parsed = JSON.parse(e.target.value || '{}');
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                  onChange(parsed);
                  setBad(false);
                } else setBad(true);
              } catch {
                setBad(true);
              }
            }}
          />
        </Field>
        {fields?.length > 0 && (
          <button type="button" className="text-xs text-indigo-600 hover:underline" onClick={() => setRaw(false)}>
            Back to the form
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {fields.map((f) => {
        const v = value?.[f.key] ?? '';
        const label = `${f.label || f.key}${f.required ? ' *' : ''}`;
        if (f.type === 'boolean') return <Checkbox key={f.key} label={label} checked={!!v} onChange={(e) => set(f.key, e.target.checked)} />;
        return (
          <Field key={f.key} label={label}>
            {f.type === 'textarea' ? (
              <Textarea rows={5} className="font-sans" value={v} onChange={(e) => set(f.key, e.target.value)} />
            ) : f.type === 'select' ? (
              <Select value={v} onChange={(e) => set(f.key, e.target.value)}>
                <option value="">Choose…</option>
                {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </Select>
            ) : (
              <Input
                type={f.type === 'number' ? 'number' : f.type === 'email' ? 'email' : f.type === 'date' ? 'date' : 'text'}
                value={v}
                onChange={(e) => set(f.key, f.type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value)}
              />
            )}
          </Field>
        );
      })}
      <button type="button" className="text-xs text-gray-500 hover:underline" onClick={() => { setText(JSON.stringify(value || {}, null, 2)); setRaw(true); }}>
        Edit as JSON
      </button>
    </div>
  );
}

export function missingRequired(fields, value) {
  return (fields || []).filter((f) => f.required && (value?.[f.key] === undefined || value?.[f.key] === '')).map((f) => f.label || f.key);
}
