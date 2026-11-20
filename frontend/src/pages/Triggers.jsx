import { useCallback, useEffect, useState } from 'react';
import { Clock, Copy, FileText, KeyRound, Plus, Trash2, Webhook } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Checkbox, Field, Input, Modal, Textarea, formatDate } from '../lib/ui';
import RunForm from './automation/RunForm';
import SchedulePicker, { describeCron } from './automation/SchedulePicker';

const KINDS = {
  form: { label: 'Form link', icon: FileText, help: 'A link anyone can open to fill in the Start form, no sign-in needed.' },
  schedule: { label: 'Schedule', icon: Clock, help: 'Runs automatically at the times you choose.' },
  webhook: { label: 'Webhook', icon: Webhook, help: 'Other systems start it by calling a URL (for IT / developers).' },
};

function copy(text) {
  navigator.clipboard?.writeText(text);
}

export default function Triggers({ workflow, isLive, fields = [], onClose }) {
  const [triggers, setTriggers] = useState([]);
  const [form, setForm] = useState(null);
  const [secret, setSecret] = useState(null); // {id, type, token} shown once
  const [error, setError] = useState('');

  const load = useCallback(
    () => api.get('/triggers', { params: { workflow_group_id: workflow.group_id } }).then((r) => setTriggers(r.data)),
    [workflow.group_id],
  );
  useEffect(() => {
    load();
  }, [load]);

  const origin = window.location.origin;
  const hookUrl = (id) => `${origin}/api/hooks/${id}`;
  const formUrl = (id, token) => `${origin}/#/f/${id}/${token}`;

  const save = async () => {
    setError('');
    const body = {
      name: form.name || KINDS[form.type].label,
      workflow_group_id: workflow.group_id,
      type: form.type,
      cron: form.type === 'schedule' ? form.cron : null,
      timezone: form.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      input: form.input || {},
      is_enabled: form.is_enabled,
      options: form.type === 'form' ? form.options : null,
    };
    try {
      if (form.id) await api.put(`/triggers/${form.id}`, body);
      else {
        const res = (await api.post('/triggers', body)).data;
        if (res.webhook_token) setSecret({ id: res.id, type: res.type, token: res.webhook_token });
      }
      setForm(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const rotate = async (t) => {
    if (!confirm(t.type === 'form' ? 'Create a new link? The old link stops working immediately.' : 'Rotate the token? The old token stops working immediately.')) return;
    const res = (await api.post(`/triggers/${t.id}/rotate-token`)).data;
    setSecret({ id: res.id, type: res.type, token: res.webhook_token });
  };

  const remove = async (t) => {
    if (!confirm(`Delete "${t.name}"?`)) return;
    await api.delete(`/triggers/${t.id}`);
    load();
  };

  const toggle = async (t) => {
    await api.put(`/triggers/${t.id}`, { ...t, is_enabled: !t.is_enabled });
    load();
  };

  const startNew = (type) => setForm({ type, name: '', cron: '0 9 * * 1-5', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', input: {}, is_enabled: true, options: { title: workflow.name, intro: '', success_message: '', show_result: false } });

  return (
    <Modal wide title={`How “${workflow.name}” starts`} onClose={onClose}>
      <div className="space-y-4">
        {!isLive && <Alert kind="info">This workflow is not live yet. Anything you add here starts working once you <b>Publish</b>.</Alert>}
        <p className="text-sm text-gray-500">People can always run it from the Workflows list or from chat. Add more ways below.</p>
        {!form && <Alert>{error}</Alert>}
        {secret && (
          <Alert kind="success">
            <div className="space-y-2">
              {secret.type === 'form' ? (
                <>
                  <div className="font-medium">Share this link. Copy it now - it is shown only once (you can create a new one later).</div>
                  <code className="block break-all rounded bg-white p-2 text-xs text-gray-800">{formUrl(secret.id, secret.token)}</code>
                  <Button variant="secondary" icon={Copy} onClick={() => copy(formUrl(secret.id, secret.token))}>Copy link</Button>
                </>
              ) : (
                <>
                  <div className="font-medium">Webhook ready. Copy the token now - it is shown only once.</div>
                  <code className="block break-all rounded bg-white p-2 text-xs text-gray-800">{secret.token}</code>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" icon={Copy} onClick={() => copy(secret.token)}>Copy token</Button>
                    <Button variant="secondary" icon={Copy} onClick={() => copy(hookUrl(secret.id))}>Copy URL</Button>
                    <Button variant="secondary" icon={Copy} onClick={() => copy(`curl -X POST ${hookUrl(secret.id)} -H "X-Webhook-Token: ${secret.token}" -H "Content-Type: application/json" -d '${JSON.stringify(Object.fromEntries(fields.map((f) => [f.key, f.type === 'number' ? 1 : 'example'])))}'`)}>Copy example (curl)</Button>
                  </div>
                </>
              )}
            </div>
          </Alert>
        )}

        {triggers.map((t) => {
          const K = KINDS[t.type] || KINDS.webhook;
          return (
            <div key={t.id} className="flex flex-wrap items-center gap-3 rounded-md border p-3 text-sm">
              <K.icon className="h-4 w-4 text-gray-500" />
              <span className="font-medium">{t.name}</span>
              <Badge color={t.type === 'schedule' ? 'blue' : t.type === 'form' ? 'green' : 'indigo'}>{K.label}</Badge>
              {t.type === 'schedule' && <span className="text-xs text-gray-600">{describeCron(t.cron)} ({t.timezone}) · next {formatDate(t.next_run_at)}</span>}
              {t.type === 'webhook' && (
                <button className="font-mono text-xs text-indigo-600 hover:underline" onClick={() => copy(hookUrl(t.id))} title="Copy URL">{hookUrl(t.id)}</button>
              )}
              {!t.is_enabled && <Badge color="red">paused</Badge>}
              <span className="text-xs text-gray-400">last run {formatDate(t.last_run_at)}</span>
              <div className="ml-auto flex gap-1">
                <Button variant="ghost" onClick={() => toggle(t)}>{t.is_enabled ? 'Pause' : 'Resume'}</Button>
                {t.type !== 'schedule' && <Button variant="ghost" icon={KeyRound} onClick={() => rotate(t)}>{t.type === 'form' ? 'New link' : 'New token'}</Button>}
                <Button variant="ghost" onClick={() => setForm({ ...t, input: t.input || {}, options: t.options || {} })}>Edit</Button>
                <Button variant="danger" icon={Trash2} onClick={() => remove(t)} aria-label="Delete" />
              </div>
            </div>
          );
        })}

        {form ? (
          <div className="space-y-3 rounded-md border bg-gray-50 p-4">
            <div className="flex items-center gap-2 font-medium text-gray-800">
              {(() => { const I = KINDS[form.type].icon; return <I className="h-4 w-4" />; })()} {KINDS[form.type].label}
            </div>
            <p className="text-xs text-gray-500">{KINDS[form.type].help}</p>
            <Field label="Name">
              <Input value={form.name} placeholder={KINDS[form.type].label} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            {form.type === 'schedule' && (
              <>
                <SchedulePicker cron={form.cron} onChange={(cron) => setForm({ ...form, cron })} />
                <Field label="Timezone" hint="e.g. Asia/Kolkata, Europe/London">
                  <Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
                </Field>
                {fields.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-medium text-gray-600">Values to use each time (nobody fills in the form on a schedule)</div>
                    <RunForm fields={fields} value={form.input} onChange={(input) => setForm({ ...form, input })} />
                  </div>
                )}
              </>
            )}
            {form.type === 'form' && (
              <>
                <Field label="Form title"><Input value={form.options?.title || ''} onChange={(e) => setForm({ ...form, options: { ...form.options, title: e.target.value } })} /></Field>
                <Field label="Introduction (optional)"><Textarea rows={2} className="font-sans" value={form.options?.intro || ''} onChange={(e) => setForm({ ...form, options: { ...form.options, intro: e.target.value } })} /></Field>
                <Field label="Message after submitting (optional)"><Input value={form.options?.success_message || ''} placeholder="Thank you - your submission was received." onChange={(e) => setForm({ ...form, options: { ...form.options, success_message: e.target.value } })} /></Field>
                <Checkbox label="Show the workflow's result to the person who submitted" checked={!!form.options?.show_result} onChange={(e) => setForm({ ...form, options: { ...form.options, show_result: e.target.checked } })} />
                {!fields.length && <Alert kind="info">The Start step has no form fields yet. Add fields to the Start step so the form asks for something.</Alert>}
              </>
            )}
            {form.type === 'webhook' && <p className="text-xs text-gray-500">The JSON body of each call is used as the form values.</p>}
            <div className="flex gap-2">
              {error && <div className="flex-1"><Alert>{error}</Alert></div>}
              <Button onClick={save}>{form.id ? 'Save' : 'Add'}</Button>
              <Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(KINDS).map(([type, k]) => (
              <Button key={type} variant="secondary" icon={Plus} onClick={() => startNew(type)}>{k.label}</Button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
