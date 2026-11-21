import { useCallback, useEffect, useState } from 'react';
import { Plug, Plus } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Checkbox, Field, Input, Modal, PageHeader, Select, Table } from '../lib/ui';

const ROLES = ['user', 'builder', 'admin'];

export default function Models() {
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [providerForm, setProviderForm] = useState(null);
  const [modelForm, setModelForm] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    api.get('/models/providers').then((r) => setProviders(r.data));
    api.get('/models').then((r) => setModels(r.data));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const test = async (p) => {
    setNotice({ kind: 'info', text: `Testing ${p.name}…` });
    try {
      const r = (await api.post(`/models/providers/${p.id}/test`)).data;
      setNotice(r.ok ? { kind: 'success', text: `${p.name} / ${r.model} replied: “${r.reply}”` } : { kind: 'error', text: `${p.name} / ${r.model}: ${r.error}` });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    }
  };

  const remove = async (path, label) => {
    if (!confirm(`Delete ${label}?`)) return;
    try {
      await api.delete(path);
      load();
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    }
  };

  const providerName = (id) => providers.find((p) => p.id === id)?.name || id;

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Models" subtitle="Any OpenAI-compatible endpoint: Ollama (/v1), vLLM, LM Studio, or a hosted API." />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Providers</h2>
            <Button icon={Plus} onClick={() => setProviderForm({ name: '', base_url: 'http://ollama:11434/v1', api_key_env: '', is_active: true })}>
              Add provider
            </Button>
          </div>
          <Table
            rows={providers}
            columns={[
              { key: 'name', label: 'Name' },
              { key: 'base_url', label: 'Base URL', className: 'font-mono text-xs' },
              { key: 'api_key_env', label: 'API key env var', render: (p) => p.api_key_env || <span className="text-gray-400">none</span> },
              { key: 'is_active', label: 'Status', render: (p) => (p.is_active ? <Badge color="green">active</Badge> : <Badge color="red">disabled</Badge>) },
              {
                key: 'actions',
                label: '',
                render: (p) => (
                  <div className="flex gap-1">
                    <Button variant="ghost" icon={Plug} onClick={() => test(p)}>Test</Button>
                    <Button variant="ghost" onClick={() => setProviderForm({ ...p, api_key_env: p.api_key_env || '' })}>Edit</Button>
                    <Button variant="ghost" onClick={() => remove(`/models/providers/${p.id}`, `provider ${p.name}`)}>Delete</Button>
                  </div>
                ),
              },
            ]}
          />
        </section>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Models</h2>
            <Button icon={Plus} disabled={!providers.length} onClick={() => setModelForm({ provider_id: providers[0]?.id, model_name: '', display_name: '', supports_tools: true, is_default: false, is_active: true, allowed_roles: [] })}>
              Add model
            </Button>
          </div>
          <Table
            rows={models}
            columns={[
              { key: 'display_name', label: 'Name', render: (m) => <>{m.display_name} {m.is_default && <Badge color="indigo">default</Badge>}</> },
              { key: 'model_name', label: 'Model id', className: 'font-mono text-xs' },
              { key: 'provider', label: 'Provider', render: (m) => providerName(m.provider_id) },
              { key: 'supports_tools', label: 'Tools', render: (m) => (m.supports_tools ? 'yes' : 'no') },
              { key: 'allowed_roles', label: 'Allowed roles', render: (m) => (m.allowed_roles.length ? m.allowed_roles.join(', ') : 'all') },
              { key: 'is_active', label: 'Status', render: (m) => (m.is_active ? <Badge color="green">active</Badge> : <Badge color="red">disabled</Badge>) },
              {
                key: 'actions',
                label: '',
                render: (m) => (
                  <div className="flex gap-1">
                    <Button variant="ghost" onClick={() => setModelForm(m)}>Edit</Button>
                    <Button variant="ghost" onClick={() => remove(`/models/${m.id}`, `model ${m.display_name}`)}>Delete</Button>
                  </div>
                ),
              },
            ]}
          />
          <p className="text-xs text-gray-500">
            Agents only get tools when their model supports tool calling. With Ollama, use a tool-capable model such as qwen2.5 or llama3.1 and
            pull it on the Ollama server first (<code>ollama pull qwen2.5:7b-instruct</code>).
          </p>
        </section>
      </div>

      {providerForm && <ProviderForm value={providerForm} onClose={() => setProviderForm(null)} onSaved={() => { setProviderForm(null); load(); }} />}
      {modelForm && <ModelForm value={modelForm} providers={providers} onClose={() => setModelForm(null)} onSaved={() => { setModelForm(null); load(); }} />}
    </div>
  );
}

function ProviderForm({ value, onClose, onSaved }) {
  const [f, setF] = useState(value);
  const [error, setError] = useState('');
  const save = async () => {
    try {
      const body = { name: f.name, base_url: f.base_url, api_key_env: f.api_key_env || null, is_active: f.is_active };
      if (f.id) await api.put(`/models/providers/${f.id}`, body);
      else await api.post('/models/providers', body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Modal title={f.id ? 'Edit provider' : 'Add provider'} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Base URL" hint="Must end with /v1 for Ollama and vLLM, e.g. http://ollama:11434/v1"><Input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} /></Field>
        <Field label="API key environment variable" hint="Optional. The NAME of an env var on the server holding the key. It must start with LLM_KEY_ (e.g. LLM_KEY_VLLM). Keys are never stored in the database.">
          <Input value={f.api_key_env} onChange={(e) => setF({ ...f, api_key_env: e.target.value.toUpperCase() })} placeholder="LLM_KEY_..." />
        </Field>
        <Checkbox label="Active" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
      </div>
    </Modal>
  );
}

function ModelForm({ value, providers, onClose, onSaved }) {
  const [f, setF] = useState(value);
  const [error, setError] = useState('');
  const toggleRole = (r) => setF({ ...f, allowed_roles: f.allowed_roles.includes(r) ? f.allowed_roles.filter((x) => x !== r) : [...f.allowed_roles, r] });
  const save = async () => {
    try {
      const body = { provider_id: Number(f.provider_id), model_name: f.model_name, display_name: f.display_name || f.model_name, supports_tools: f.supports_tools, is_default: f.is_default, is_active: f.is_active, allowed_roles: f.allowed_roles };
      if (f.id) await api.put(`/models/${f.id}`, body);
      else await api.post('/models', body);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Modal title={f.id ? 'Edit model' : 'Add model'} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} disabled={!f.model_name}>Save</Button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <Field label="Provider">
          <Select value={f.provider_id} onChange={(e) => setF({ ...f, provider_id: e.target.value })}>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
        <Field label="Model id" hint="Exactly as the server knows it, e.g. qwen2.5:7b-instruct"><Input value={f.model_name} onChange={(e) => setF({ ...f, model_name: e.target.value })} /></Field>
        <Field label="Display name"><Input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        <div className="flex flex-wrap gap-4">
          <Checkbox label="Supports tool calling" checked={f.supports_tools} onChange={(e) => setF({ ...f, supports_tools: e.target.checked })} />
          <Checkbox label="Default model" checked={f.is_default} onChange={(e) => setF({ ...f, is_default: e.target.checked })} />
          <Checkbox label="Active" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
        </div>
        <div>
          <div className="mb-1 text-xs font-medium text-gray-600">Allowed roles (none ticked = everyone)</div>
          <div className="flex gap-4">
            {ROLES.map((r) => <Checkbox key={r} label={r} checked={f.allowed_roles.includes(r)} onChange={() => toggleRole(r)} />)}
          </div>
        </div>
      </div>
    </Modal>
  );
}
