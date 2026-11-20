import { useCallback, useMemo, useState } from 'react';
import { Background, Controls, Handle, Position, ReactFlow, addEdge, useEdgesState, useNodesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft, CheckCircle2, CircleCheck, CircleDashed, CircleX, Clock, Flag, FlaskConical, GitBranch, Play, Plus, Power,
  Rocket, Save, Search, Split, Trash2, X,
} from 'lucide-react';
import api, { errorMessage } from '../../lib/api';
import { can } from '../../lib/auth';
import { CATEGORY_STYLE, iconFor } from '../../lib/icons';
import { Alert, Button, Checkbox, Field, Input, Modal, Select, StatusBadge, Textarea, cx } from '../../lib/ui';
import RunSteps, { ResultView } from '../RunSteps';
import Triggers from '../Triggers';
import RunForm, { missingRequired } from './RunForm';
import StepForm, { VarText, availableVariables } from './StepForm';

const OPERATORS = [
  ['==', 'is equal to'], ['!=', 'is not equal to'], ['>', 'is greater than'], ['<', 'is less than'],
  ['>=', 'is at least'], ['<=', 'is at most'], ['contains', 'contains'], ['not_contains', 'does not contain'],
  ['starts_with', 'starts with'], ['is_empty', 'is empty'], ['not_empty', 'is not empty'],
];
const LOGIC = [
  { type: 'condition', name: 'If / else', description: 'Go one way or another based on a value.', icon: GitBranch },
  { type: 'switch', name: 'Switch', description: 'Route to one of several paths (e.g. by category).', icon: Split },
  { type: 'end', name: 'Finish', description: 'End of a path; choose what the automation returns.', icon: Flag },
];
const STATUS_ICON = { success: CircleCheck, failed: CircleX, error_continued: CircleX, skipped: CircleDashed };
const STATUS_COLOR = { success: 'text-green-600', failed: 'text-red-600', error_continued: 'text-amber-600', skipped: 'text-gray-400' };

function meta(node, catalog) {
  if (node.type === 'input') return { title: 'Start', icon: Play, style: CATEGORY_STYLE.Start };
  if (node.type === 'end') return { title: 'Finish', icon: Flag, style: CATEGORY_STYLE.Finish };
  if (node.type === 'condition') return { title: 'If / else', icon: GitBranch, style: CATEGORY_STYLE.Flow };
  if (node.type === 'switch') return { title: 'Switch', icon: Split, style: CATEGORY_STYLE.Flow };
  const nt = catalog.find((n) => n.key === node.data?.action);
  return { title: nt?.name || 'Step', icon: iconFor(nt?.icon), style: CATEGORY_STYLE[nt?.category] || CATEGORY_STYLE.Flow };
}

function StepNode({ data, type, selected }) {
  const m = data._meta || {};
  const Icon = m.icon || Play;
  const StatusIcon = STATUS_ICON[data._status];
  const cases = type === 'switch' ? [...(data.cases || []).filter((c) => String(c).trim()), 'default'] : [];
  return (
    <div className={cx('w-56 rounded-lg border-2 bg-white px-3 py-2 shadow-sm', selected ? m.style?.border : 'border-gray-200')}>
      {type !== 'input' && <Handle type="target" position={Position.Top} />}
      <div className="flex items-center gap-2">
        <div className={cx('rounded-md p-1.5', m.style?.bg)}>
          <Icon className={cx('h-4 w-4', m.style?.text)} />
        </div>
        <div className="min-w-0 flex-1">
          <div className={cx('text-[10px] font-semibold uppercase tracking-wide', m.style?.text)}>{m.title}</div>
          <div className="truncate text-sm text-gray-900">{data.label || m.title}</div>
        </div>
        {StatusIcon && <StatusIcon className={cx('h-4 w-4 flex-shrink-0', STATUS_COLOR[data._status])} />}
      </div>
      {type === 'condition' && (
        <>
          <Handle type="source" position={Position.Bottom} id="true" style={{ left: '28%', background: '#16a34a' }} />
          <Handle type="source" position={Position.Bottom} id="false" style={{ left: '72%', background: '#dc2626' }} />
          <div className="mt-1 flex justify-between px-6 text-[10px] font-semibold"><span className="text-green-700">Yes</span><span className="text-red-700">No</span></div>
        </>
      )}
      {type === 'switch' && (
        <>
          {cases.map((c, i) => (
            <Handle key={c} type="source" position={Position.Bottom} id={String(c).toLowerCase() === 'default' ? 'default' : c} style={{ left: `${((i + 1) * 100) / (cases.length + 1)}%`, background: c === 'default' ? '#6b7280' : '#d97706' }} />
          ))}
          <div className="mt-1 flex justify-around text-[10px] font-semibold text-amber-700">
            {cases.map((c) => <span key={c} className="max-w-[4rem] truncate">{c}</span>)}
          </div>
        </>
      )}
      {type !== 'end' && type !== 'condition' && type !== 'switch' && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

const nodeTypes = { input: StepNode, action: StepNode, condition: StepNode, switch: StepNode, end: StepNode, agent: StepNode, tool: StepNode, transform: StepNode };

function newId() {
  return `s${Date.now().toString(36).slice(-4)}${Math.random().toString(36).slice(2, 4)}`;
}

function blank() {
  return {
    nodes: [
      { id: 'start', type: 'input', position: { x: 300, y: 40 }, data: { label: 'Start', fields: [] } },
      { id: 'finish', type: 'end', position: { x: 300, y: 320 }, data: { label: 'Finish' } },
    ],
    edges: [{ id: 'e-start-finish', source: 'start', target: 'finish' }],
  };
}

export default function FlowBuilder({ workflow, draft, catalog, credentialTypes, agents, user, onBack, onSaved }) {
  const initial = draft?.definition || (workflow?.definition?.nodes?.length ? workflow.definition : blank());
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [current, setCurrent] = useState(workflow);
  const [name, setName] = useState(draft?.name || workflow?.name || 'New automation');
  const [meta_, setMeta] = useState({
    description: draft?.description || workflow?.description || '',
    trigger_keywords: workflow?.trigger_keywords || '',
    visibility: workflow?.visibility || 'private',
  });
  const [selectedId, setSelectedId] = useState(null);
  const [notice, setNotice] = useState(draft?.warnings?.length ? { kind: 'info', text: `Drafted by AI. Still to do: ${draft.warnings.join(' • ')}` } : null);
  const [busy, setBusy] = useState('');
  const [dirty, setDirty] = useState(!!draft);
  const [testOpen, setTestOpen] = useState(false);
  const [triggersOpen, setTriggersOpen] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [paletteQuery, setPaletteQuery] = useState('');

  const editable = !current || current.can_edit;
  const isDraft = !current || current.status === 'draft';
  const selected = nodes.find((n) => n.id === selectedId);
  const startNode = nodes.find((n) => n.type === 'input');
  const stepResults = useMemo(() => Object.fromEntries((lastRun?.steps || []).map((s) => [s.node_id, s])), [lastRun]);

  // Decorate nodes with icon/title and last test status for rendering.
  const viewNodes = useMemo(
    () => nodes.map((n) => ({ ...n, data: { ...n.data, _meta: meta(n, catalog), _status: stepResults[n.id]?.status } })),
    [nodes, catalog, stepResults],
  );

  // Selecting or measuring nodes is not an edit; only moves, additions and removals are.
  const change = (fn) => (changes) => {
    if (changes.some((c) => c.type === 'remove' || c.type === 'add' || (c.type === 'position' && c.dragging))) setDirty(true);
    return fn(changes);
  };

  const onConnect = useCallback(
    (params) => {
      setDirty(true);
      setEdges((eds) => addEdge({ ...params, label: params.sourceHandle && params.sourceHandle !== 'null' ? (params.sourceHandle === 'true' ? 'Yes' : params.sourceHandle === 'false' ? 'No' : params.sourceHandle) : undefined }, eds));
    },
    [setEdges],
  );

  const updateData = (id, patch) => {
    setDirty(true);
    setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
  };

  /** Add a step. If a plain step is selected, insert the new one right after it. */
  const addStep = (type, action) => {
    const id = newId();
    const nt = catalog.find((n) => n.key === action);
    const data =
      type === 'action' ? { label: nt?.name || 'Step', action, config: {}, settings: {} }
        : type === 'condition' ? { label: 'Check', condition: { left: '', operator: '==', right: '' } }
          : type === 'switch' ? { label: 'Route', value: '', cases: ['option 1', 'option 2'] }
            : { label: 'Finish' };
    const anchor = selected && !['end', 'condition', 'switch'].includes(selected.type) ? selected : null;
    const position = anchor ? { x: anchor.position.x, y: anchor.position.y + 130 } : { x: 300 + (nodes.length % 3) * 40, y: 160 + nodes.length * 30 };
    setDirty(true);
    setNodes((nds) => {
      const shifted = anchor ? nds.map((n) => (n.position.y > anchor.position.y ? { ...n, position: { ...n.position, y: n.position.y + 130 } } : n)) : nds;
      return [...shifted, { id, type, position, data }];
    });
    if (anchor) {
      setEdges((eds) => {
        const outgoing = eds.filter((e) => e.source === anchor.id);
        const rest = eds.filter((e) => e.source !== anchor.id);
        const moved = type === 'end' ? [] : outgoing.map((e) => ({ ...e, id: `e-${id}-${e.target}`, source: id, sourceHandle: type === 'condition' ? 'true' : type === 'switch' ? 'default' : null, label: type === 'condition' ? 'Yes' : type === 'switch' ? 'default' : undefined }));
        return [...rest, { id: `e-${anchor.id}-${id}`, source: anchor.id, target: id }, ...moved];
      });
    }
    setSelectedId(id);
  };

  const removeSelected = () => {
    setDirty(true);
    const incoming = edges.filter((e) => e.target === selectedId);
    const outgoing = edges.filter((e) => e.source === selectedId);
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) => {
      const kept = eds.filter((e) => e.source !== selectedId && e.target !== selectedId);
      // Re-join a simple chain (A -> X -> B becomes A -> B).
      if (incoming.length === 1 && outgoing.length === 1 && !['condition', 'switch'].includes(selected?.type)) {
        kept.push({ ...incoming[0], id: `e-${incoming[0].source}-${outgoing[0].target}`, target: outgoing[0].target });
      }
      return kept;
    });
    setSelectedId(null);
  };

  const definition = () => ({
    nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
    edges: edges.map(({ id, source, target, sourceHandle, label }) => ({ id, source, target, sourceHandle: sourceHandle || null, label: label || null })),
  });

  const body = () => ({ name, description: meta_.description || null, trigger_keywords: meta_.trigger_keywords || null, visibility: meta_.visibility, definition: definition() });

  const save = async () => {
    setBusy('save');
    try {
      const saved = current && isDraft ? (await api.put(`/workflows/${current.id}`, body())).data : (await api.post('/workflows', { ...body(), group_id: current?.group_id })).data;
      const newVersion = current && saved.id !== current.id;
      setCurrent(saved);
      setDirty(false);
      onSaved?.();
      setNotice({ kind: 'success', text: newVersion ? `Saved as a new draft (version ${saved.version}). The live version keeps running until you publish this one.` : 'Saved.' });
      return saved;
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
      return null;
    } finally {
      setBusy('');
    }
  };

  const ensureSaved = async () => (dirty || !current ? await save() : current);

  const check = async () => {
    const wf = await ensureSaved();
    if (!wf) return null;
    const res = (await api.post(`/workflows/${wf.id}/validate`)).data;
    setNotice(res.is_valid ? { kind: 'success', text: 'Everything looks good.' } : { kind: 'error', text: res.errors.join(' • ') });
    return res.is_valid ? wf : null;
  };

  const publish = async () => {
    setBusy('publish');
    try {
      const wf = await check();
      if (!wf) return;
      const res = (await api.post(`/workflows/${wf.id}/activate`)).data;
      setCurrent(res);
      onSaved?.();
      setNotice({ kind: 'success', text: `Published. Version ${res.version} is now live.` });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    } finally {
      setBusy('');
    }
  };

  const unpublish = async () => {
    if (!confirm('Turn this automation off? Schedules and webhooks will stop starting it.')) return;
    try {
      const res = (await api.post(`/workflows/${current.id}/deactivate`)).data;
      setCurrent(res);
      onSaved?.();
      setNotice({ kind: 'info', text: 'Turned off.' });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    }
  };

  const openTest = async () => {
    const wf = await ensureSaved();
    if (wf) setTestOpen(true);
  };

  const groups = selected ? availableVariables(selected.id, nodes, edges, catalog) : [];
  const q = paletteQuery.trim().toLowerCase();
  const palette = catalog.filter((n) => !n.disabled && (!q || `${n.name} ${n.description}`.toLowerCase().includes(q)));
  const categories = ['AI', 'Apps', 'Data', 'Flow'];

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b bg-white px-4 py-2.5">
        <Button variant="ghost" icon={ArrowLeft} onClick={() => (!dirty || confirm('Leave without saving?')) && onBack()}>
          Back
        </Button>
        <Input className="max-w-xs font-medium" value={name} disabled={!editable} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        {current ? <StatusBadge status={current.status === 'active' ? 'active' : current.status} /> : <StatusBadge status="draft" />}
        {current && <span className="text-xs text-gray-400">v{current.version}</span>}
        {dirty && <span className="text-xs text-amber-600">unsaved changes</span>}
        <div className="ml-auto flex flex-wrap gap-2">
          {editable && <Button variant="secondary" icon={Save} loading={busy === 'save'} onClick={save}>Save</Button>}
          {editable && <Button variant="secondary" icon={FlaskConical} onClick={openTest}>Test</Button>}
          {current && editable && can(user, 'trigger:write') && <Button variant="secondary" icon={Clock} onClick={() => setTriggersOpen(true)}>Schedule & webhooks</Button>}
          {editable && can(user, 'workflow:activate') && (current?.status === 'active' && !dirty ? (
            <Button variant="secondary" icon={Power} onClick={unpublish}>Turn off</Button>
          ) : (
            <Button icon={Rocket} loading={busy === 'publish'} onClick={publish}>Publish</Button>
          ))}
        </div>
      </div>
      {notice && (
        <div className="flex items-start gap-2 border-b bg-white px-4 py-2">
          <div className="flex-1"><Alert kind={notice.kind}>{notice.text}</Alert></div>
          <button onClick={() => setNotice(null)} className="p-1 text-gray-400" aria-label="Dismiss"><X className="h-4 w-4" /></button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {editable && (
          <div className="flex w-60 flex-shrink-0 flex-col border-r bg-white">
            <div className="p-3 pb-2">
              <div className="mb-2 text-xs font-semibold uppercase text-gray-400">Add a step</div>
              <div className="relative">
                <Search className="absolute left-2 top-2 h-4 w-4 text-gray-400" />
                <input className="w-full rounded-md border py-1.5 pl-7 pr-2 text-sm" placeholder="Search steps" value={paletteQuery} onChange={(e) => setPaletteQuery(e.target.value)} />
              </div>
              {selected && !['end', 'condition', 'switch'].includes(selected.type) && <p className="mt-2 text-xs text-gray-400">Added after “{selected.data?.label}”</p>}
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-3 pb-3">
              {categories.map((cat) => {
                const items = palette.filter((n) => n.category === cat);
                const logic = cat === 'Flow' ? LOGIC.filter((l) => !q || `${l.name} ${l.description}`.toLowerCase().includes(q)) : [];
                if (!items.length && !logic.length) return null;
                const st = CATEGORY_STYLE[cat];
                return (
                  <div key={cat}>
                    <div className={cx('mb-1 text-[11px] font-semibold uppercase', st.text)}>{cat === 'Flow' ? 'Logic & flow' : cat}</div>
                    {[...logic.map((l) => ({ ...l, onClick: () => addStep(l.type), Icon: l.icon, key: l.type })),
                      ...items.map((n) => ({ ...n, onClick: () => addStep('action', n.key), Icon: iconFor(n.icon) }))].map((it) => (
                      <button key={it.key} onClick={it.onClick} title={it.description} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-50">
                        <span className={cx('rounded p-1', st.bg)}><it.Icon className={cx('h-3.5 w-3.5', st.text)} /></span>
                        <span className="truncate">{it.name}</span>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="min-w-0 flex-1">
          <ReactFlow
            nodes={viewNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={editable ? change(onNodesChange) : undefined}
            onEdgesChange={editable ? change(onEdgesChange) : undefined}
            onConnect={editable ? onConnect : undefined}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            nodesDraggable={editable}
            nodesConnectable={editable}
            deleteKeyCode={editable ? ['Delete'] : null}
            fitView
            fitViewOptions={{ maxZoom: 1 }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <div className="w-96 flex-shrink-0 overflow-y-auto border-l bg-white p-4">
          {selected ? (
            <fieldset disabled={!editable} className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">{meta(selected, catalog).title}</h3>
                {editable && selected.type !== 'input' && <Button variant="danger" icon={Trash2} onClick={removeSelected}>Remove</Button>}
              </div>
              {selected.type === 'action' && <p className="-mt-2 text-sm text-gray-500">{catalog.find((n) => n.key === selected.data?.action)?.description}</p>}
              <Field label="Name of this step">
                <Input value={selected.data?.label || ''} onChange={(e) => updateData(selected.id, { label: e.target.value })} />
              </Field>
              <NodeSettings node={selected} catalog={catalog} groups={groups} agents={agents} credentialTypes={credentialTypes} onChange={(patch) => updateData(selected.id, patch)} onTriggers={current ? () => setTriggersOpen(true) : null} />
              {stepResults[selected.id] && <StepResult step={stepResults[selected.id]} />}
            </fieldset>
          ) : (
            <AutomationSettings meta={meta_} setMeta={(m) => { setMeta(m); setDirty(true); }} editable={editable} lastRun={lastRun} />
          )}
        </div>
      </div>

      {testOpen && current && (
        <TestRun workflow={current} fields={startNode?.data?.fields || []} onClose={() => setTestOpen(false)} onResult={(run) => { setLastRun(run); setNotice(run.status === 'succeeded' ? { kind: 'success', text: 'Test succeeded. Click a step to see what it produced.' } : { kind: 'error', text: run.error }); }} />
      )}
      {triggersOpen && current && <Triggers workflow={current} onClose={() => setTriggersOpen(false)} />}
    </div>
  );
}

function StepResult({ step }) {
  return (
    <div className="rounded-md border bg-gray-50 p-3">
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-gray-500">
        Last test <StatusBadge status={step.status === 'success' ? 'succeeded' : step.status} />
        {step.attempts > 1 && <span className="normal-case">{step.attempts} attempts</span>}
      </div>
      {step.error && <p className="mb-1 text-sm text-red-600">{step.error}</p>}
      {step.output !== undefined && <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs text-gray-800">{JSON.stringify(step.output, null, 2)}</pre>}
    </div>
  );
}

function AutomationSettings({ meta, setMeta, editable, lastRun }) {
  return (
    <fieldset disabled={!editable} className="space-y-3">
      <h3 className="font-semibold text-gray-900">About this automation</h3>
      <Field label="Description">
        <Textarea rows={3} className="font-sans" value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} />
      </Field>
      <Field label="Who can run it">
        <Select value={meta.visibility} onChange={(e) => setMeta({ ...meta, visibility: e.target.value })}>
          <option value="private">Only me</option>
          <option value="department">My department</option>
          <option value="public">Everyone</option>
        </Select>
      </Field>
      <Field label="Chat keywords (optional)" hint="Comma separated. Chat messages containing one run this automation.">
        <Input value={meta.trigger_keywords} onChange={(e) => setMeta({ ...meta, trigger_keywords: e.target.value })} />
      </Field>
      <div className="rounded-md bg-indigo-50 p-3 text-sm text-indigo-900">
        <b>Tips</b>
        <ul className="mt-1 list-disc space-y-1 pl-4">
          <li>Click a step to set it up. Use <i>Insert data</i> to use results from earlier steps.</li>
          <li>Select a step, then pick a new one on the left to insert it right after.</li>
          <li><b>Test</b> runs your draft; <b>Publish</b> makes it live for schedules, webhooks and chat.</li>
        </ul>
      </div>
      {lastRun && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-gray-500">Last test result</div>
          <pre className="max-h-60 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{JSON.stringify(lastRun.output?.result ?? lastRun.error, null, 2)}</pre>
        </div>
      )}
    </fieldset>
  );
}

const FORM_TYPES = [['text', 'Short text'], ['textarea', 'Long text'], ['number', 'Number'], ['email', 'Email'], ['date', 'Date'], ['select', 'Choice'], ['boolean', 'Yes / no']];

function NodeSettings({ node, catalog, groups, agents, credentialTypes, onChange, onTriggers }) {
  const data = node.data || {};

  if (node.type === 'input') {
    const fields = data.fields || [];
    const setFields = (f) => onChange({ fields: f });
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-600">
          An automation starts when someone runs it (they fill in the form below), from chat, on a schedule, or from a webhook.
        </p>
        {onTriggers && <Button variant="secondary" icon={Clock} onClick={onTriggers}>Add a schedule or webhook</Button>}
        <div className="text-xs font-semibold uppercase text-gray-500">Form fields</div>
        {!fields.length && <p className="text-xs text-gray-400">No fields. Add some so people can give the automation information when they run it.</p>}
        {fields.map((f, i) => (
          <div key={i} className="space-y-1.5 rounded-md border bg-gray-50 p-2">
            <div className="flex gap-1">
              <Input placeholder="Label" value={f.label} onChange={(e) => {
                const label = e.target.value;
                const key = f.keyEdited ? f.key : label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || `field_${i + 1}`;
                setFields(fields.map((x, j) => (j === i ? { ...x, label, key } : x)));
              }} />
              <button type="button" className="p-1 text-gray-400 hover:text-red-600" onClick={() => setFields(fields.filter((_, j) => j !== i))} aria-label="Remove field"><X className="h-4 w-4" /></button>
            </div>
            <div className="flex gap-1">
              <Select value={f.type} onChange={(e) => setFields(fields.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))}>
                {FORM_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
              <Checkbox label="Required" checked={!!f.required} onChange={(e) => setFields(fields.map((x, j) => (j === i ? { ...x, required: e.target.checked } : x)))} />
            </div>
            {f.type === 'select' && (
              <Input placeholder="Choices, comma separated" value={(f.options || []).join(', ')} onChange={(e) => setFields(fields.map((x, j) => (j === i ? { ...x, options: e.target.value.split(',').map((s) => s.trim()) } : x)))} />
            )}
            <p className="font-mono text-[11px] text-gray-400">{`{{input.${f.key}}}`}</p>
          </div>
        ))}
        <Button variant="secondary" icon={Plus} onClick={() => setFields([...fields, { key: `field_${fields.length + 1}`, label: '', type: 'text', required: false }])}>Add field</Button>
      </div>
    );
  }

  if (node.type === 'action') {
    const nt = catalog.find((n) => n.key === data.action);
    if (!nt) return <Alert>This step type is not available (it may have been disabled by an administrator).</Alert>;
    const settings = data.settings || {};
    return (
      <div className="space-y-4">
        <StepForm nodeType={nt} config={data.config || {}} onChange={(config) => onChange({ config })} groups={groups} agents={agents} credentialTypes={credentialTypes} />
        <details className="rounded-md border p-2 text-sm">
          <summary className="cursor-pointer text-gray-600">If this step fails…</summary>
          <div className="mt-2 space-y-2">
            <div className="flex gap-2">
              <Field label="Retry times" className="flex-1">
                <Select value={settings.retries || 0} onChange={(e) => onChange({ settings: { ...settings, retries: Number(e.target.value) } })}>
                  {[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n === 0 ? "Don't retry" : n}</option>)}
                </Select>
              </Field>
              <Field label="Wait between (seconds)" className="flex-1">
                <Input type="number" min="0" max="60" value={settings.retry_delay_seconds ?? 1} onChange={(e) => onChange({ settings: { ...settings, retry_delay_seconds: Number(e.target.value) } })} />
              </Field>
            </div>
            <Checkbox label="Keep going anyway (the step's output becomes { error })" checked={!!settings.continue_on_error} onChange={(e) => onChange({ settings: { ...settings, continue_on_error: e.target.checked } })} />
          </div>
        </details>
        {nt.output_hint && <p className="text-xs text-gray-500">Produces: <code>{nt.output_hint}</code></p>}
      </div>
    );
  }

  if (node.type === 'condition') {
    const cond = data.condition || { left: '', operator: '==', right: '' };
    const set = (patch) => onChange({ condition: { ...cond, ...patch } });
    const asText = (v) => (typeof v === 'object' && v ? v.value ?? (v.path ? `{{input.${v.path}}}` : '') : v);
    return (
      <div className="space-y-3">
        <Field label="If this value"><VarText value={asText(cond.left)} groups={groups} placeholder="{{input.amount}}" onChange={(v) => set({ left: v })} /></Field>
        <Field label="…">
          <Select value={cond.operator} onChange={(e) => set({ operator: e.target.value })}>
            {OPERATORS.map(([o, l]) => <option key={o} value={o}>{l}</option>)}
          </Select>
        </Field>
        {!['is_empty', 'not_empty'].includes(cond.operator) && <Field label="this value"><VarText value={asText(cond.right)} groups={groups} placeholder="1000" onChange={(v) => set({ right: v })} /></Field>}
        <p className="text-xs text-gray-500">Connect the green <b>Yes</b> handle and the red <b>No</b> handle to the next steps.</p>
      </div>
    );
  }

  if (node.type === 'switch') {
    const cases = data.cases || [];
    return (
      <div className="space-y-3">
        <Field label="Route by this value"><VarText value={data.value || ''} groups={groups} placeholder="{{classify.category}}" onChange={(v) => onChange({ value: v })} /></Field>
        <div className="text-xs font-semibold uppercase text-gray-500">Paths</div>
        {cases.map((c, i) => (
          <div key={i} className="flex gap-1">
            <Input value={c} onChange={(e) => onChange({ cases: cases.map((x, j) => (j === i ? e.target.value : x)) })} />
            <button type="button" className="p-1 text-gray-400 hover:text-red-600" onClick={() => onChange({ cases: cases.filter((_, j) => j !== i) })} aria-label="Remove path"><X className="h-4 w-4" /></button>
          </div>
        ))}
        <Button variant="secondary" icon={Plus} onClick={() => onChange({ cases: [...cases, `option ${cases.length + 1}`] })}>Add path</Button>
        <p className="text-xs text-gray-500">Each path gets its own handle under the step; anything else goes to <b>default</b>. Matching ignores upper/lower case.</p>
      </div>
    );
  }

  if (node.type === 'end') {
    return (
      <Field label="Result to return (optional)" hint="Leave empty to return what the previous step produced.">
        <VarText multiline rows={3} value={data.config?.output || ''} groups={groups} onChange={(v) => onChange({ config: { output: v } })} />
      </Field>
    );
  }

  return <p className="text-sm text-gray-500">This is an older step type. It still runs, but cannot be edited here.</p>;
}

function TestRun({ workflow, fields, onClose, onResult }) {
  const [input, setInput] = useState({});
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const go = async () => {
    const missing = missingRequired(fields, input);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ')}`);
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = (await api.post(`/workflows/${workflow.id}/test`, { input })).data;
      setRun(res);
      onResult(res);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal wide title={`Test “${workflow.name}”`} onClose={onClose} footer={run ? <Button onClick={onClose}>Show on canvas</Button> : null}>
      <div className="space-y-3">
        <RunForm fields={fields} value={input} onChange={setInput} />
        <Button icon={FlaskConical} loading={loading} onClick={go}>Run test</Button>
        <Alert>{error}</Alert>
        {run && (
          <>
            <Alert kind={run.status === 'succeeded' ? 'success' : 'error'}>
              {run.status === 'succeeded' ? <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> Succeeded</span> : run.error}
            </Alert>
            {run.output && <ResultView value={run.output.result} />}
            <RunSteps steps={run.steps} />
          </>
        )}
      </div>
    </Modal>
  );
}
