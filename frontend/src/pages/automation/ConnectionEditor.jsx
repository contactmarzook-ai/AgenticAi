import { useState } from 'react';
import api, { errorMessage } from '../../lib/api';
import { Alert, Button, Field, Input, Modal, Select } from '../../lib/ui';

/** Create or edit a saved connection. Secret fields are never shown again after saving. */
export default function ConnectionEditor({ types, existing, onClose, onSaved }) {
  const [type, setType] = useState(existing?.type || types[0]?.key || '');
  const [name, setName] = useState(existing?.name || '');
  const [visibility, setVisibility] = useState(existing?.visibility || 'private');
  const [data, setData] = useState(existing?.public_data || {});
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const ctype = types.find((t) => t.key === type);

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const body = { name, type, visibility, data };
      const res = existing ? await api.put(`/credentials/${existing.id}`, body) : await api.post('/credentials', body);
      onSaved(res.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={existing ? `Edit connection: ${existing.name}` : 'New connection'}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!name.trim() || !ctype}>Save connection</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Alert>{error}</Alert>
        {!existing && types.length > 1 && (
          <Field label="Type">
            <Select value={type} onChange={(e) => { setType(e.target.value); setData({}); }}>
              {types.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
            </Select>
          </Field>
        )}
        {ctype?.help && <p className="text-sm text-gray-500">{ctype.help}</p>}
        <Field label="Name" hint="So you can recognise it, e.g. 'Support mailbox'">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        {ctype?.fields.map((f) => (
          <Field
            key={f.key}
            label={`${f.label}${f.required ? ' *' : ''}`}
            hint={f.secret && existing ? 'Saved. Leave empty to keep it.' : f.help}
          >
            {f.type === 'select' ? (
              <Select value={data[f.key] ?? f.default ?? ''} onChange={(e) => setData({ ...data, [f.key]: e.target.value })}>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </Select>
            ) : (
              <Input
                type={f.secret ? 'password' : f.type === 'number' ? 'number' : 'text'}
                autoComplete="off"
                placeholder={f.placeholder || (f.default != null ? String(f.default) : '')}
                value={data[f.key] ?? ''}
                onChange={(e) => setData({ ...data, [f.key]: f.type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value })}
              />
            )}
          </Field>
        ))}
        <Field label="Who can use it in their automations">
          <Select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
            <option value="private">Only me</option>
            <option value="department">My department</option>
            <option value="public">Everyone</option>
          </Select>
        </Field>
        <p className="text-xs text-gray-400">Secrets are encrypted and never displayed again.</p>
      </div>
    </Modal>
  );
}
