import { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Checkbox, Field, Input, Modal, Select, Textarea, formatDate } from '../lib/ui';

const BLANK = { name: '', type: 'schedule', cron: '0 9 * * 1-5', timezone: 'UTC', input: '{}', is_enabled: true };

export default function Triggers({ workflow, onClose }) {
  const [triggers, setTriggers] = useState([]);
  const [form, setForm] = useState(null);
  const [token, setToken] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(
    () => api.get('/triggers', { params: { workflow_group_id: workflow.group_id } }).then((r) => setTriggers(r.data)),
    [workflow.group_id],
  );
  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setError('');
    let input;
    try {
      input = JSON.parse(form.input || '{}');
    } catch {
      setError('Default input must be valid JSON');
      return;
    }
    const body = { name: form.name, workflow_group_id: workflow.group_id, type: form.type, cron: form.type === 'schedule' ? form.cron : null, timezone: form.timezone, input, is_enabled: form.is_enabled };
    try {
      if (form.id) {
        await api.put(`/triggers/${form.id}`, body);
      } else {
        const res = (await api.post('/triggers', body)).data;
        if (res.webhook_token) setToken({ id: res.id, token: res.webhook_token });
      }
      setForm(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const rotate = async (t) => {
    if (!confirm('Rotate the token? The old token stops working immediately.')) return;
    const res = (await api.post(`/triggers/${t.id}/rotate-token`)).data;
    setToken({ id: res.id, token: res.webhook_token });
  };

  const remove = async (t) => {
    if (!confirm(`Delete trigger "${t.name}"?`)) return;
    await api.delete(`/triggers/${t.id}`);
    load();
  };

  const hookUrl = (id) => `${window.location.origin}/api/hooks/${id}`;

  return (
    <Modal wide title={`Schedule & webhooks: “${workflow.name}”`} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-gray-500">These start the <b>published</b> version of this automation automatically. Publish it first.</p>
        <Alert>{error}</Alert>
        {token && (
          <Alert kind="success">
            <div className="space-y-1">
              <div className="font-medium">Webhook token — copy it now, it will not be shown again.</div>
              <code className="block break-all rounded bg-white p-2 text-xs text-gray-800">{token.token}</code>
              <div className="text-xs">
                Call: <code>POST {hookUrl(token.id)}</code> with header <code>X-Webhook-Token</code> and a JSON object body.
              </div>
              <Button variant="secondary" icon={Copy} onClick={() => navigator.clipboard?.writeText(token.token)}>
                Copy token
              </Button>
            </div>
          </Alert>
        )}

        {triggers.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center gap-3 rounded-md border p-3 text-sm">
            <Badge color={t.type === 'schedule' ? 'blue' : 'indigo'}>{t.type}</Badge>
            <span className="font-medium">{t.name}</span>
            {t.type === 'schedule' ? (
              <span className="font-mono text-xs text-gray-600">
                {t.cron} ({t.timezone}) · next {formatDate(t.next_run_at)}
              </span>
            ) : (
              <span className="font-mono text-xs text-gray-600">{hookUrl(t.id)}</span>
            )}
            {!t.is_enabled && <Badge color="red">disabled</Badge>}
            <span className="text-xs text-gray-400">last run {formatDate(t.last_run_at)}</span>
            <div className="ml-auto flex gap-1">
              {t.type === 'webhook' && (
                <Button variant="ghost" icon={KeyRound} onClick={() => rotate(t)}>
                  Rotate token
                </Button>
              )}
              <Button variant="ghost" onClick={() => setForm({ ...t, input: JSON.stringify(t.input, null, 2), cron: t.cron || '' })}>
                Edit
              </Button>
              <Button variant="danger" icon={Trash2} onClick={() => remove(t)} aria-label="Delete trigger" />
            </div>
          </div>
        ))}

        {form ? (
          <div className="space-y-3 rounded-md border bg-gray-50 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Name">
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
              <Field label="Type">
                <Select value={form.type} disabled={!!form.id} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                  <option value="schedule">Schedule (cron)</option>
                  <option value="webhook">Webhook</option>
                </Select>
              </Field>
              {form.type === 'schedule' && (
                <>
                  <Field label="Cron expression" hint="minute hour day month weekday — e.g. 0 9 * * 1-5 = 09:00 on weekdays">
                    <Input className="font-mono" value={form.cron} onChange={(e) => setForm({ ...form, cron: e.target.value })} />
                  </Field>
                  <Field label="Timezone" hint="IANA name, e.g. Asia/Kolkata">
                    <Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
                  </Field>
                </>
              )}
            </div>
            <Field label="Default input (JSON)" hint={form.type === 'webhook' ? 'Merged with the webhook request body.' : undefined}>
              <Textarea rows={3} value={form.input} onChange={(e) => setForm({ ...form, input: e.target.value })} />
            </Field>
            <Checkbox label="Enabled" checked={form.is_enabled} onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} />
            <div className="flex gap-2">
              <Button onClick={save} disabled={!form.name}>
                Save trigger
              </Button>
              <Button variant="secondary" onClick={() => setForm(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" icon={Plus} onClick={() => setForm({ ...BLANK })}>
            Add trigger
          </Button>
        )}
      </div>
    </Modal>
  );
}
