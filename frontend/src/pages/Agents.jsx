import { useCallback, useEffect, useState } from 'react';
import { Bot, CheckCircle2, Pencil, Play, Plus, Wrench, XCircle } from 'lucide-react';
import { isAdmin } from '../lib/roles';
import api, { errorMessage } from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Badge, Button, Checkbox, Empty, Field, Input, Modal, PageHeader, Select, Textarea } from '../lib/ui';
import RunSteps, { ResultView } from './RunSteps';
import SchemaEditor, { SchemaForm } from './agents/SchemaEditor';

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
  capabilities: [],
  tags: [],
};

const isSimpleInput = (schema) => {
  const props = Object.keys(schema?.properties || {});
  return props.length === 1 && props[0] === 'message';
};
const splitSlugs = (text) => text.split(',').map((s) => s.trim().toLowerCase().replace(/\s+/g, '-')).filter(Boolean);

export default function Agents({ user }) {
  const canWrite = can(user, 'agent:write');
  const [agents, setAgents] = useState([]);
  const [models, setModels] = useState([]);
  const [tools, setTools] = useState([]);
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState(null);
  const [trying, setTrying] = useState(null);
  const [error, setError] = useState('');
  const [defaults, setDefaults] = useState(null);

  const load = useCallback(() => {
    api.get('/agents', { params: { include_inactive: showInactive } }).then((r) => setAgents(r.data)).catch((e) => setError(errorMessage(e)));
  }, [showInactive]);

  useEffect(() => {
    load();
    api.get('/agents/contract-defaults').then((r) => setDefaults(r.data)).catch(() => {});
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
              <Button icon={Plus} disabled={!defaults} onClick={() => setEditing({ ...BLANK, ...defaults })}>
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
              <div key={a.id} className="glass glass-hover flex flex-col rounded-lg border p-4 shadow-card">
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
                {(a.capabilities.length > 0 || a.tags.length > 0) && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {a.capabilities.map((c) => <Badge key={c} color="indigo">{c}</Badge>)}
                    {a.tags.map((t) => <Badge key={t}>#{t}</Badge>)}
                  </div>
                )}
                <p className="mb-2 text-xs text-muted-strong" title="Input fields → output fields">
                  <span className="font-medium">Contract:</span> {Object.keys(a.input_schema.properties || {}).join(', ') || '—'} → {Object.keys(a.output_schema.properties || {}).join(', ') || '—'}
                </p>
                <div className="mb-3 flex flex-wrap gap-1">
                  {a.tools.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 rounded bg-navy-50/60 px-1.5 ring-1 ring-inset ring-line py-0.5 font-mono text-xs text-muted-strong">
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
      {editing && <AgentEditor agent={editing} defaults={defaults} models={models} tools={tools} user={user} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {trying && <TryAgent agent={trying} onClose={() => setTrying(null)} />}
    </div>
  );
}

function AgentEditor({ agent, defaults, models, tools, user, onClose, onSaved }) {
  const [form, setForm] = useState({ ...agent, capabilitiesText: (agent.capabilities || []).join(', '), tagsText: (agent.tags || []).join(', ') });
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
      input_schema: form.input_schema,
      output_schema: form.output_schema,
      capabilities: splitSlugs(form.capabilitiesText),
      tags: splitSlugs(form.tagsText),
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
          <Field label="Department" hint={isAdmin(user) ? 'Admins can set any department.' : 'Always your own department.'}>
            <Input value={isAdmin(user) ? form.department : user.department || ''} disabled={!isAdmin(user)} onChange={(e) => set('department', e.target.value)} />
          </Field>
          <div className="pt-6">
            <Checkbox label="Enabled" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Capabilities" hint="What it can do, comma separated, e.g. invoice.extract, order.lookup. The chat router and workflow builders use these to find agents.">
            <Input value={form.capabilitiesText} onChange={(e) => set('capabilitiesText', e.target.value)} placeholder="order.lookup" />
          </Field>
          <Field label="Tags" hint="Free labels for finding agents, e.g. finance, hr.">
            <Input value={form.tagsText} onChange={(e) => set('tagsText', e.target.value)} placeholder="sales" />
          </Field>
        </div>
        <details className="rounded-md border p-3 text-sm" open={!isSimpleInput(form.input_schema) || JSON.stringify(form.output_schema) !== JSON.stringify(defaults?.output_schema)}>
          <summary className="cursor-pointer text-muted-strong">Input and output contract</summary>
          <p className="mt-2 text-xs text-muted-strong">
            What the agent accepts and what it must return. Inputs are checked before it runs; its answer is checked against the output fields (it gets one chance to fix a wrong answer, then the run fails).
          </p>
          <div className="mt-3 space-y-4">
            <div data-contract="input">
              <div className="mb-1 text-xs font-semibold text-navy">Input</div>
              <SchemaEditor value={form.input_schema} onChange={(v) => set('input_schema', v)} defaultSchema={defaults?.input_schema} simpleLabel="a single message" />
            </div>
            <div data-contract="output">
              <div className="mb-1 text-xs font-semibold text-navy">Output</div>
              <SchemaEditor value={form.output_schema} onChange={(v) => set('output_schema', v)} defaultSchema={defaults?.output_schema} simpleLabel="a text answer" />
            </div>
          </div>
        </details>
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
  const simple = isSimpleInput(agent.input_schema);
  const [message, setMessage] = useState('');
  const [input, setInput] = useState({});
  const [asJson, setAsJson] = useState(false);
  const [jsonText, setJsonText] = useState('{}');
  const [inputCheck, setInputCheck] = useState(null); // {valid, errors}
  const [run, setRun] = useState(null);
  const [elapsed, setElapsed] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const payload = () => {
    if (simple) return { message };
    if (asJson) {
      try {
        return JSON.parse(jsonText);
      } catch {
        return jsonText; // the server reports "must be an object"
      }
    }
    return input;
  };

  const checkInput = async () => {
    setError('');
    try {
      const r = await api.post(`/agents/${agent.id}/check`, { input: payload() });
      setInputCheck(r.data.input);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const go = async () => {
    setLoading(true);
    setError('');
    setRun(null);
    setInputCheck(null);
    const t0 = performance.now();
    try {
      const r = await api.post(`/agents/${agent.id}/run`, { input: payload() });
      setRun(r.data);
      setInputCheck({ valid: true, errors: [] });
    } catch (err) {
      const fields = err.response?.status === 422 ? err.response.data?.detail?.fields : null;
      if (fields) setInputCheck({ valid: false, errors: fields });
      else setError(errorMessage(err));
    } finally {
      setElapsed(Math.round(performance.now() - t0));
      setLoading(false);
    }
  };

  const outputChecks = (run?.steps || []).filter((s) => s.type === 'validation' && s.stage === 'output');
  const lastOutput = outputChecks[outputChecks.length - 1];
  const duration = run?.started_at && run?.finished_at ? new Date(run.finished_at) - new Date(run.started_at) : elapsed;

  return (
    <Modal wide title={`Test ${agent.name}`} onClose={onClose}>
      <div className="space-y-4">
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-navy">Input</h3>
            {!simple && (
              <button type="button" className="text-xs text-brand-600 hover:underline" onClick={() => { setJsonText(JSON.stringify(input, null, 2)); setAsJson(!asJson); }}>
                {asJson ? 'Use the form' : 'Edit as JSON'}
              </button>
            )}
          </div>
          {simple ? (
            <Textarea rows={3} placeholder="Ask the agent something…" value={message} onChange={(e) => setMessage(e.target.value)} className="font-sans" />
          ) : asJson ? (
            <Textarea rows={8} className="font-mono text-xs" value={jsonText} onChange={(e) => setJsonText(e.target.value)} aria-label="Input JSON" />
          ) : (
            <SchemaForm schema={agent.input_schema} value={input} onChange={setInput} />
          )}
          <div className="mt-2 flex gap-2">
            <Button icon={Play} onClick={go} loading={loading} disabled={simple && !message.trim()}>Run</Button>
            {!simple && <Button variant="secondary" onClick={checkInput}>Check input</Button>}
          </div>
        </section>
        <Alert>{error}</Alert>
        {inputCheck && <ValidationResult title="Input validation" check={inputCheck} />}
        {run && (
          <>
            <section className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-navy-50/60 px-3 py-2 text-sm">
              <span className="font-medium text-navy">Execution</span>
              <Badge color={run.status === 'succeeded' ? 'green' : 'red'}>{run.status}</Badge>
              {duration != null && <span className="text-muted-strong">{(duration / 1000).toFixed(2)} s</span>}
              <span className="text-xs text-muted-strong">{run.model_name} · {run.llm_calls} LLM calls · {run.prompt_tokens + run.completion_tokens} tokens</span>
            </section>
            {run.output && (
              <section>
                <h3 className="mb-1 text-sm font-semibold text-navy">Output</h3>
                <ResultView value={Object.keys(run.output).length === 1 && 'answer' in run.output ? run.output.answer : run.output} />
              </section>
            )}
            {lastOutput && (
              <ValidationResult
                title={`Output validation${outputChecks.length > 1 ? ` (${outputChecks.length} attempts)` : ''}`}
                check={lastOutput}
                note={outputChecks.length > 1 && lastOutput.valid ? 'The first answer did not match; the agent corrected it.' : null}
              />
            )}
            {run.error && (
              <section>
                <h3 className="mb-1 text-sm font-semibold text-navy">Error details</h3>
                <Alert>{run.error}</Alert>
              </section>
            )}
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-strong">Steps ({run.steps.length})</summary>
              <div className="mt-2"><RunSteps steps={run.steps} /></div>
            </details>
          </>
        )}
      </div>
    </Modal>
  );
}

function ValidationResult({ title, check, note }) {
  return (
    <section className={check.valid ? 'rounded-md border border-green-200 bg-green-50 p-3 text-sm' : 'rounded-md border border-red-200 bg-red-50 p-3 text-sm'}>
      <div className="flex items-center gap-2 font-medium">
        {check.valid ? <CheckCircle2 className="h-4 w-4 text-green-700" /> : <XCircle className="h-4 w-4 text-red-700" />}
        <span className={check.valid ? 'text-green-800' : 'text-red-800'}>{title}: {check.valid ? 'passed' : 'failed'}</span>
      </div>
      {note && <p className="mt-1 text-xs text-green-800">{note}</p>}
      {!check.valid && (
        <ul className="mt-1 space-y-0.5 text-xs text-red-800">
          {check.errors.map((e, i) => (
            <li key={i}><span className="font-mono">{e.path}</span>: {e.message}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
