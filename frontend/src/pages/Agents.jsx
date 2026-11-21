import { useCallback, useEffect, useState } from 'react';
import { Bot, Pencil, Play, Plus, Wrench } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Badge, Button, Checkbox, Empty, Field, Input, Modal, PageHeader, Select, Textarea } from '../lib/ui';
import RunSteps from './RunSteps';

const BLANK = {
  name: '',
  description: '',
  system_prompt: 'You are a helpful assistant for our organisation. Use the tools you have when they help. Be concise.',
  model_id: '',
  tools: [],
  trigger_keywords: '',
  temperature: 0.2,
  max_steps: 6,
  visibility: 'department',
  department: '',
  is_active: true,
};

export default function Agents({ user }) {
  const canWrite = can(user, 'agent:write');
  const [agents, setAgents] = useState([]);
  const [models, setModels] = useState([]);
  const [tools, setTools] = useState([]);
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState(null);
  const [trying, setTrying] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api.get('/agents', { params: { include_inactive: showInactive } }).then((r) => setAgents(r.data)).catch((e) => setError(errorMessage(e)));
  }, [showInactive]);

  useEffect(() => {
    load();
    if (canWrite) {
      api.get('/models').then((r) => setModels(r.data));
      api.get('/tools').then((r) => setTools(r.data));
    }
  }, [load, canWrite]);

  const modelName = (id) => models.find((m) => m.id === id)?.display_name || (id ? `model #${id}` : 'default model');

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Agents"
        subtitle="An agent is a system prompt, a model and a set of tools it may call."
        actions={
          <>
            {canWrite && <Checkbox label="Show disabled" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />}
            {canWrite && (
              <Button icon={Plus} onClick={() => setEditing({ ...BLANK })}>
                New agent
              </Button>
            )}
          </>
        }
      />
      <div className="flex-1 overflow-y-auto p-6">
        <Alert>{error}</Alert>
        {!agents.length ? (
          <Empty>{canWrite ? 'No agents yet. Create one to get started.' : 'No agents are shared with you yet.'}</Empty>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {agents.map((a) => (
              <div key={a.id} className="flex flex-col rounded-lg border bg-surface p-4 shadow-card">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="rounded-md bg-brand-50 p-1.5">
                      <Bot className="h-4 w-4 text-brand-600" />
                    </div>
                    <h3 className="font-semibold text-navy">{a.name}</h3>
                  </div>
                  <div className="flex gap-1">
                    {!a.is_active && <Badge color="red">disabled</Badge>}
                    <Badge color={a.visibility === 'public' ? 'green' : a.visibility === 'private' ? 'gray' : 'blue'}>
                      {a.visibility}
                      {a.visibility === 'department' && a.department ? `: ${a.department}` : ''}
                    </Badge>
                  </div>
                </div>
                <p className="mb-3 line-clamp-3 flex-1 text-sm text-muted-strong">{a.description || 'No description.'}</p>
                <div className="mb-3 flex flex-wrap gap-1">
                  {a.tools.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 rounded bg-app px-1.5 ring-1 ring-inset ring-line py-0.5 font-mono text-xs text-muted-strong">
                      <Wrench className="h-3 w-3" />
                      {t}
                    </span>
                  ))}
                  {canWrite && <span className="text-xs text-muted-strong">{modelName(a.model_id)}</span>}
                </div>
                <div className="flex gap-2">
                  {a.is_active && can(user, 'agent:run') && (
                    <Button variant="secondary" icon={Play} onClick={() => setTrying(a)}>
                      Try
                    </Button>
                  )}
                  {a.can_edit && (
                    <Button variant="ghost" icon={Pencil} onClick={() => setEditing({ ...a, model_id: a.model_id ?? '', department: a.department ?? '', trigger_keywords: a.trigger_keywords ?? '', description: a.description ?? '' })}>
                      Edit
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {editing && <AgentEditor agent={editing} models={models} tools={tools} user={user} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {trying && <TryAgent agent={trying} onClose={() => setTrying(null)} />}
    </div>
  );
}

function AgentEditor({ agent, models, tools, user, onClose, onSaved }) {
  const [form, setForm] = useState(agent);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const selectedModel = models.find((m) => m.id === Number(form.model_id)) || models.find((m) => m.is_default);
  const toolsBlocked = selectedModel && !selectedModel.supports_tools;

  const toggleTool = (name) => set('tools', form.tools.includes(name) ? form.tools.filter((t) => t !== name) : [...form.tools, name]);

  const save = async () => {
    setSaving(true);
    setError('');
    const body = {
      name: form.name,
      description: form.description || null,
      system_prompt: form.system_prompt,
      model_id: form.model_id === '' ? null : Number(form.model_id),
      tools: form.tools,
      trigger_keywords: form.trigger_keywords || null,
      temperature: Number(form.temperature),
      max_steps: Number(form.max_steps),
      visibility: form.visibility,
      department: form.department || null,
      is_active: form.is_active,
    };
    try {
      if (form.id) await api.put(`/agents/${form.id}`, body);
      else await api.post('/agents', body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      wide
      title={form.id ? `Edit agent: ${agent.name}` : 'New agent'}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={saving} disabled={!form.name.trim()}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Alert>{error}</Alert>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Name">
            <Input value={form.name} onChange={(e) => set('name', e.target.value)} />
          </Field>
          <Field label="Model" hint="Leave on default to use the platform's default model.">
            <Select value={form.model_id} onChange={(e) => set('model_id', e.target.value)}>
              <option value="">Platform default</option>
              {models.filter((m) => m.is_active).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                  {m.supports_tools ? '' : ' (no tool calling)'}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Description" hint="Shown to users, and used by the router to decide when to pick this agent.">
          <Input value={form.description} onChange={(e) => set('description', e.target.value)} />
        </Field>
        <Field label="System prompt">
          <Textarea rows={6} value={form.system_prompt} onChange={(e) => set('system_prompt', e.target.value)} />
        </Field>
        <div>
          <div className="mb-1 text-xs font-medium text-muted-strong">Tools</div>
          {toolsBlocked && <Alert kind="info">The selected model does not support tool calling, so tools are disabled.</Alert>}
          <div className="grid gap-2 md:grid-cols-2">
            {tools.map((t) => (
              <label key={t.name} className="flex cursor-pointer gap-2 rounded-md border p-2 text-sm hover:bg-brand-50">
                <input type="checkbox" className="mt-0.5" disabled={toolsBlocked} checked={form.tools.includes(t.name)} onChange={() => toggleTool(t.name)} />
                <span>
                  <span className="font-medium text-ink">{t.description.split(':')[0]}</span>
                  <span className="block text-xs text-muted-strong">{t.description.split(':').slice(1).join(':').trim() || t.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Who can use it">
            <Select value={form.visibility} onChange={(e) => set('visibility', e.target.value)}>
              <option value="private">Only me (and admins)</option>
              <option value="department">My department</option>
              <option value="public">Everyone</option>
            </Select>
          </Field>
          <Field label="Department" hint={user.role === 'admin' ? 'Admins can set any department.' : 'Always your own department.'}>
            <Input value={user.role === 'admin' ? form.department : user.department || ''} disabled={user.role !== 'admin'} onChange={(e) => set('department', e.target.value)} />
          </Field>
          <div className="pt-6">
            <Checkbox label="Enabled" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} />
          </div>
        </div>
        <details className="rounded-md border p-3 text-sm">
          <summary className="cursor-pointer text-muted-strong">Advanced</summary>
          <div className="mt-3">
            <div className="grid gap-4 md:grid-cols-3">
          <Field label="Chat keywords" hint="Comma separated. Messages containing one go straight to this agent (otherwise the AI decides).">
            <Input value={form.trigger_keywords} onChange={(e) => set('trigger_keywords', e.target.value)} />
          </Field>
          <Field label="Temperature">
            <Input type="number" min="0" max="2" step="0.1" value={form.temperature} onChange={(e) => set('temperature', e.target.value)} />
          </Field>
          <Field label="Max tool steps">
            <Input type="number" min="1" max="50" value={form.max_steps} onChange={(e) => set('max_steps', e.target.value)} />
          </Field>
        </div>
          </div>
        </details>
      </div>
    </Modal>
  );
}

function TryAgent({ agent, onClose }) {
  const [message, setMessage] = useState('');
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const go = async () => {
    setLoading(true);
    setError('');
    setRun(null);
    try {
      setRun((await api.post(`/agents/${agent.id}/run`, { message })).data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal wide title={`Try ${agent.name}`} onClose={onClose}>
      <div className="space-y-3">
        <Textarea rows={3} placeholder="Ask the agent something…" value={message} onChange={(e) => setMessage(e.target.value)} className="font-sans" />
        <Button icon={Play} onClick={go} loading={loading} disabled={!message.trim()}>
          Run
        </Button>
        <Alert>{error}</Alert>
        {run && (
          <div className="space-y-3">
            {run.status === 'succeeded' ? (
              <div className="whitespace-pre-wrap rounded-md border bg-app p-3 text-sm">{run.output?.answer}</div>
            ) : (
              <Alert>{run.error}</Alert>
            )}
            <p className="text-xs text-muted-strong">
              {run.model_name} · {run.llm_calls} LLM calls · {run.prompt_tokens + run.completion_tokens} tokens
            </p>
            <RunSteps steps={run.steps} />
          </div>
        )}
      </div>
    </Modal>
  );
}
