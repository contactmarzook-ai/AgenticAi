import { useCallback, useMemo, useState } from 'react';
import { Background, Controls, Handle, MiniMap, Position, ReactFlow, addEdge, useEdgesState, useNodesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ArrowLeft, CheckCircle2, Clock, FlaskConical, Plus, Rocket, Save, Trash2 } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Button, Field, Input, Modal, Select, StatusBadge, Textarea, cx } from '../lib/ui';
import MappingEditor from './MappingEditor';
import RunSteps from './RunSteps';
import Triggers from './Triggers';

const NODE_STYLES = {
  input: { title: 'Input', border: 'border-green-500', text: 'text-green-700' },
  agent: { title: 'Agent', border: 'border-indigo-500', text: 'text-indigo-700' },
  tool: { title: 'Tool', border: 'border-blue-500', text: 'text-blue-700' },
  condition: { title: 'Condition', border: 'border-orange-500', text: 'text-orange-700' },
  transform: { title: 'Transform', border: 'border-purple-500', text: 'text-purple-700' },
  end: { title: 'End', border: 'border-gray-800', text: 'text-gray-800' },
};

function makeNode(type) {
  const s = NODE_STYLES[type];
  return function NodeView({ data, selected }) {
    return (
      <div className={cx('w-48 rounded-md border-2 bg-white p-2.5 shadow-sm', selected ? s.border : 'border-gray-300')}>
        {type !== 'input' && <Handle type="target" position={Position.Top} />}
        <div className={cx('text-xs font-bold uppercase tracking-wide', s.text)}>{s.title}</div>
        <div className="truncate text-sm text-gray-800">{data.label || data.summary || '—'}</div>
        {type === 'condition' ? (
          <>
            <Handle type="source" position={Position.Bottom} id="true" style={{ left: '25%', background: '#16a34a' }} />
            <Handle type="source" position={Position.Bottom} id="false" style={{ left: '75%', background: '#dc2626' }} />
            <div className="mt-1 flex justify-between px-3 text-[10px] font-semibold">
              <span className="text-green-700">true</span>
              <span className="text-red-700">false</span>
            </div>
          </>
        ) : (
          type !== 'end' && <Handle type="source" position={Position.Bottom} />
        )}
      </div>
    );
  };
}

const nodeTypes = Object.fromEntries(Object.keys(NODE_STYLES).map((t) => [t, makeNode(t)]));

const OPERATORS = [
  ['==', 'equals'],
  ['!=', 'does not equal'],
  ['>', 'greater than'],
  ['<', 'less than'],
  ['>=', 'at least'],
  ['<=', 'at most'],
  ['contains', 'contains'],
  ['is_empty', 'is empty'],
  ['not_empty', 'is not empty'],
];

function newId() {
  return `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

function starterDefinition() {
  return {
    nodes: [
      { id: 'input', type: 'input', position: { x: 250, y: 40 }, data: { label: 'Workflow input' } },
      { id: 'end', type: 'end', position: { x: 250, y: 320 }, data: { label: 'Result' } },
    ],
    edges: [],
  };
}

export default function WorkflowBuilder({ workflow, agents, tools, user, onBack, onSaved }) {
  const initial = workflow?.definition?.nodes?.length ? workflow.definition : starterDefinition();
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [current, setCurrent] = useState(workflow);
  const [meta, setMeta] = useState({
    name: workflow?.name || 'New workflow',
    description: workflow?.description || '',
    trigger_keywords: workflow?.trigger_keywords || '',
    visibility: workflow?.visibility || 'department',
    department: workflow?.department || '',
  });
  const [selectedId, setSelectedId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState('');
  const [testOpen, setTestOpen] = useState(false);
  const [triggersOpen, setTriggersOpen] = useState(false);

  const editable = !current || current.can_edit;
  const isDraft = !current || current.status === 'draft';
  const selected = nodes.find((n) => n.id === selectedId);

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge({ ...params, label: params.sourceHandle || undefined }, eds)),
    [setEdges],
  );

  const updateData = (id, patch) => setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));

  const addNode = (type) => {
    const id = newId();
    setNodes((nds) => [...nds, { id, type, position: { x: 260 + (nds.length % 3) * 30, y: 120 + nds.length * 25 }, data: { label: NODE_STYLES[type].title, mappings: {} } }]);
    setSelectedId(id);
  };

  const removeSelected = () => {
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  };

  const definition = () => ({
    nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
    edges: edges.map(({ id, source, target, sourceHandle, label }) => ({ id, source, target, sourceHandle: sourceHandle || null, label: label || null })),
  });

  const body = () => ({
    name: meta.name,
    description: meta.description || null,
    trigger_keywords: meta.trigger_keywords || null,
    visibility: meta.visibility,
    department: meta.department || null,
    definition: definition(),
  });

  const flash = (kind, text) => setNotice({ kind, text });

  const save = async () => {
    setBusy('save');
    try {
      let saved;
      if (current && isDraft) saved = (await api.put(`/workflows/${current.id}`, body())).data;
      else saved = (await api.post('/workflows', { ...body(), group_id: current?.group_id })).data;
      const createdNewVersion = !current || saved.id !== current.id;
      setCurrent(saved);
      onSaved?.();
      flash('success', createdNewVersion && current ? `Saved as draft version ${saved.version}.` : 'Draft saved.');
      return saved;
    } catch (err) {
      flash('error', errorMessage(err));
      return null;
    } finally {
      setBusy('');
    }
  };

  const validate = async () => {
    const wf = isDraft || !current ? await save() : current;
    if (!wf) return;
    setBusy('validate');
    try {
      const res = (await api.post(`/workflows/${wf.id}/validate`)).data;
      flash(res.is_valid ? 'success' : 'error', res.is_valid ? 'Workflow is valid.' : res.errors.join(' • '));
    } finally {
      setBusy('');
    }
  };

  const activate = async () => {
    const wf = isDraft || !current ? await save() : current;
    if (!wf) return;
    setBusy('activate');
    try {
      const res = (await api.post(`/workflows/${wf.id}/activate`)).data;
      setCurrent(res);
      onSaved?.();
      flash('success', `Version ${res.version} is now active. Earlier versions were archived.`);
    } catch (err) {
      flash('error', errorMessage(err));
    } finally {
      setBusy('');
    }
  };

  const openTest = async () => {
    const wf = isDraft || !current ? await save() : current;
    if (wf) setTestOpen(true);
  };

  const otherNodes = useMemo(() => nodes.filter((n) => n.id !== selectedId), [nodes, selectedId]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b bg-white px-4 py-2.5">
        <Button variant="ghost" icon={ArrowLeft} onClick={onBack}>
          Workflows
        </Button>
        <Input className="max-w-xs font-medium" value={meta.name} disabled={!editable} onChange={(e) => setMeta({ ...meta, name: e.target.value })} />
        {current && (
          <span className="flex items-center gap-1 text-sm text-gray-500">
            v{current.version} <StatusBadge status={current.status} />
          </span>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          {editable && (
            <Button variant="secondary" icon={Save} loading={busy === 'save'} onClick={save}>
              {isDraft ? 'Save draft' : 'Save as new version'}
            </Button>
          )}
          <Button variant="secondary" icon={CheckCircle2} loading={busy === 'validate'} onClick={validate}>
            Validate
          </Button>
          {editable && (
            <Button variant="secondary" icon={FlaskConical} onClick={openTest}>
              Test
            </Button>
          )}
          {current && can(user, 'trigger:write') && editable && (
            <Button variant="secondary" icon={Clock} onClick={() => setTriggersOpen(true)}>
              Triggers
            </Button>
          )}
          {editable && can(user, 'workflow:activate') && current?.status !== 'active' && (
            <Button icon={Rocket} loading={busy === 'activate'} onClick={activate}>
              Activate
            </Button>
          )}
        </div>
      </div>
      {notice && (
        <div className="border-b bg-white px-4 py-2">
          <Alert kind={notice.kind}>{notice.text}</Alert>
        </div>
      )}
      {!isDraft && editable && (
        <div className="border-b bg-yellow-50 px-4 py-1.5 text-xs text-yellow-800">
          This version is {current.status}. Changes are saved as a new draft version; the {current.status} version keeps running until you activate the new one.
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {editable && (
          <div className="w-44 flex-shrink-0 space-y-1.5 border-r bg-white p-3">
            <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Add node</div>
            {['agent', 'tool', 'condition', 'transform', 'end'].map((t) => (
              <button key={t} onClick={() => addNode(t)} className={cx('flex w-full items-center gap-1.5 rounded border px-2 py-1.5 text-sm hover:bg-gray-50', NODE_STYLES[t].text)}>
                <Plus className="h-3.5 w-3.5" /> {NODE_STYLES[t].title}
              </button>
            ))}
            <div className="pt-4 text-xs text-gray-400">Drag from a node's bottom handle to another node's top handle to connect them. Select a connection and press Delete to remove it.</div>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={editable ? onNodesChange : undefined}
            onEdgesChange={editable ? onEdgesChange : undefined}
            onConnect={editable ? onConnect : undefined}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            nodesDraggable={editable}
            nodesConnectable={editable}
            deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
        <div className="w-80 flex-shrink-0 overflow-y-auto border-l bg-white p-4">
          {selected ? (
            <NodeProperties node={selected} others={otherNodes} agents={agents} tools={tools} editable={editable} onChange={(patch) => updateData(selected.id, patch)} onDelete={removeSelected} />
          ) : (
            <WorkflowProperties meta={meta} setMeta={setMeta} editable={editable} user={user} />
          )}
        </div>
      </div>

      {testOpen && current && <TestRun workflow={current} onClose={() => setTestOpen(false)} />}
      {triggersOpen && current && <Triggers workflow={current} onClose={() => setTriggersOpen(false)} />}
    </div>
  );
}

function WorkflowProperties({ meta, setMeta, editable, user }) {
  const set = (k, v) => setMeta({ ...meta, [k]: v });
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-gray-900">Workflow settings</h3>
      <Field label="Description" hint="Used by the chat router to decide when to run this workflow.">
        <Textarea rows={3} className="font-sans" disabled={!editable} value={meta.description} onChange={(e) => set('description', e.target.value)} />
      </Field>
      <Field label="Trigger keywords" hint="Comma separated; chat messages containing one run this workflow.">
        <Input disabled={!editable} value={meta.trigger_keywords} onChange={(e) => set('trigger_keywords', e.target.value)} />
      </Field>
      <Field label="Who can run it">
        <Select disabled={!editable} value={meta.visibility} onChange={(e) => set('visibility', e.target.value)}>
          <option value="private">Only me (and admins)</option>
          <option value="department">My department</option>
          <option value="public">Everyone</option>
        </Select>
      </Field>
      {user.role === 'admin' && (
        <Field label="Department">
          <Input disabled={!editable} value={meta.department} onChange={(e) => set('department', e.target.value)} />
        </Field>
      )}
      <p className="text-xs text-gray-500">Select a node to configure it. In chat, the workflow receives {'{"message": "<user text>"}'} as input.</p>
    </div>
  );
}

function NodeProperties({ node, others, agents, tools, editable, onChange, onDelete }) {
  const data = node.data || {};
  const mappings = data.mappings || {};
  const setMapping = (key, m) => onChange({ mappings: { ...mappings, [key]: m } });
  const removeMapping = (key) => {
    const next = { ...mappings };
    delete next[key];
    onChange({ mappings: next });
  };
  const tool = tools.find((t) => t.name === data.tool);

  return (
    <fieldset disabled={!editable} className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">{NODE_STYLES[node.type]?.title} node</h3>
        {editable && node.type !== 'input' && (
          <Button variant="danger" icon={Trash2} onClick={onDelete}>
            Delete
          </Button>
        )}
      </div>
      <p className="font-mono text-xs text-gray-400">id: {node.id}</p>
      <Field label="Label">
        <Input value={data.label || ''} onChange={(e) => onChange({ label: e.target.value })} />
      </Field>

      {node.type === 'input' && <p className="text-sm text-gray-500">Passes the workflow input (a JSON object) to the next nodes. Other nodes read its fields with “Workflow input field”.</p>}

      {node.type === 'agent' && (
        <>
          <Field label="Agent">
            <Select value={data.agent_id || ''} onChange={(e) => onChange({ agent_id: e.target.value ? Number(e.target.value) : null, summary: agents.find((a) => a.id === Number(e.target.value))?.name })}>
              <option value="">Select an agent…</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Message sent to the agent" hint="If left unmapped, the workflow input's “message” field is used.">
            <MappingEditor value={mappings.message} nodes={others} onChange={(m) => setMapping('message', m)} />
          </Field>
          <p className="text-xs text-gray-500">Output: {'{ "answer": "..." }'}</p>
        </>
      )}

      {node.type === 'tool' && (
        <>
          <Field label="Tool">
            <Select value={data.tool || ''} onChange={(e) => onChange({ tool: e.target.value, summary: e.target.value, mappings: {} })}>
              <option value="">Select a tool…</option>
              {tools.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
          {tool && <p className="text-xs text-gray-500">{tool.description}</p>}
          {tool &&
            Object.entries(tool.parameters.properties || {}).map(([arg, schema]) => (
              <Field key={arg} label={`${arg}${(tool.parameters.required || []).includes(arg) ? ' *' : ''} (${schema.type})`}>
                <MappingEditor value={mappings[arg]} nodes={others} onChange={(m) => setMapping(arg, m)} />
              </Field>
            ))}
        </>
      )}

      {node.type === 'condition' && <ConditionEditor data={data} others={others} onChange={onChange} />}

      {(node.type === 'transform' || node.type === 'end') && (
        <KeyedMappings mappings={mappings} others={others} setMapping={setMapping} removeMapping={removeMapping} isEnd={node.type === 'end'} />
      )}
    </fieldset>
  );
}

function ConditionEditor({ data, others, onChange }) {
  const cond = data.condition || { left: { source: 'input', path: '' }, operator: '==', right: { source: 'static', value: '' } };
  const set = (patch) => {
    const next = { ...cond, ...patch };
    const op = OPERATORS.find(([o]) => o === next.operator)?.[1];
    onChange({ condition: next, summary: `if … ${op}` });
  };
  return (
    <>
      <Field label="Value to check">
        <MappingEditor value={cond.left} nodes={others} multiline={false} onChange={(m) => set({ left: m })} />
      </Field>
      <Field label="Operator">
        <Select value={cond.operator} onChange={(e) => set({ operator: e.target.value })}>
          {OPERATORS.map(([o, label]) => (
            <option key={o} value={o}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      {!['is_empty', 'not_empty'].includes(cond.operator) && (
        <Field label="Compare with">
          <MappingEditor value={cond.right} nodes={others} multiline={false} onChange={(m) => set({ right: m })} />
        </Field>
      )}
      <p className="text-xs text-gray-500">Connect the green handle to the “true” path and the red handle to the “false” path.</p>
    </>
  );
}

function KeyedMappings({ mappings, others, setMapping, removeMapping, isEnd }) {
  const [key, setKey] = useState('');
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500">
        {isEnd
          ? 'Fields of the final result. Leave empty to return the previous node’s output.'
          : 'Builds a new object from the fields below.'}
      </p>
      {Object.entries(mappings).map(([k, m]) => (
        <div key={k}>
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-xs font-medium">{k}</span>
            <button className="text-xs text-red-600 hover:underline" onClick={() => removeMapping(k)}>
              remove
            </button>
          </div>
          <MappingEditor value={m} nodes={others} onChange={(v) => setMapping(k, v)} />
        </div>
      ))}
      <div className="flex gap-2">
        <Input placeholder="new field name" value={key} onChange={(e) => setKey(e.target.value.replace(/[^\w-]/g, ''))} />
        <Button
          variant="secondary"
          disabled={!key || key in mappings}
          onClick={() => {
            setMapping(key, { source: 'static', value: '' });
            setKey('');
          }}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

function TestRun({ workflow, onClose }) {
  const [input, setInput] = useState('{\n  "message": "Hello"\n}');
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const go = async () => {
    let parsed;
    try {
      parsed = JSON.parse(input);
    } catch {
      setError('Input must be valid JSON');
      return;
    }
    setError('');
    setRun(null);
    setLoading(true);
    try {
      setRun((await api.post(`/workflows/${workflow.id}/test`, { input: parsed })).data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal wide title={`Test “${workflow.name}” v${workflow.version}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="Workflow input (JSON object)">
          <Textarea rows={5} value={input} onChange={(e) => setInput(e.target.value)} />
        </Field>
        <Button icon={FlaskConical} loading={loading} onClick={go}>
          Run test
        </Button>
        <Alert>{error}</Alert>
        {run && (
          <>
            <Alert kind={run.status === 'succeeded' ? 'success' : 'error'}>
              {run.status === 'succeeded' ? 'Succeeded' : run.error}
            </Alert>
            {run.output && <pre className="max-h-60 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{JSON.stringify(run.output.result, null, 2)}</pre>}
            <RunSteps steps={run.steps} />
          </>
        )}
      </div>
    </Modal>
  );
}
