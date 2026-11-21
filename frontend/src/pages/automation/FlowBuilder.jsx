import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BaseEdge, Background, Controls, EdgeLabelRenderer, Handle, Position, ReactFlow, addEdge, getBezierPath, useEdgesState,
  useNodesState, useUpdateNodeInternals,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ArrowLeft, CheckCircle2, CircleCheck, CircleDashed, CircleX, Clock, Flag, FlaskConical, GitBranch, Play, Plus, Power,
  Redo2, Repeat, Rocket, Save, Search, Split, Trash2, Undo2, X,
} from 'lucide-react';
import api, { errorMessage } from '../../lib/api';
import { can } from '../../lib/auth';
import { CATEGORY_STYLE, iconFor } from '../../lib/icons';
import { useUnsaved } from '../../lib/unsaved';
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
  { type: 'loop', name: 'Repeat for each', description: 'Do one step for every item in a list.', icon: Repeat },
  { type: 'end', name: 'Finish', description: 'End of a path; choose what the workflow returns.', icon: Flag },
];
const BRANCHING = ['condition', 'switch'];
const STATUS_ICON = { success: CircleCheck, failed: CircleX, error_continued: CircleX, skipped: CircleDashed };
const STATUS_COLOR = { success: 'text-green-600', failed: 'text-red-600', error_continued: 'text-amber-600', skipped: 'text-muted-strong' };
const FORM_TYPES = [['text', 'Short text'], ['textarea', 'Long text'], ['number', 'Number'], ['email', 'Email'], ['date', 'Date'], ['select', 'Choice'], ['boolean', 'Yes / no']];

function meta(node, catalog) {
  if (node.type === 'input') return { title: 'Start', icon: Play, style: CATEGORY_STYLE.Start };
  if (node.type === 'end') return { title: 'Finish', icon: Flag, style: CATEGORY_STYLE.Finish };
  if (node.type === 'condition') return { title: 'If / else', icon: GitBranch, style: CATEGORY_STYLE.Flow };
  if (node.type === 'switch') return { title: 'Switch', icon: Split, style: CATEGORY_STYLE.Flow };
  const nt = catalog.find((n) => n.key === node.data?.action);
  if (node.type === 'loop') return { title: `Repeat: ${nt?.name || 'choose a step'}`, icon: Repeat, style: CATEGORY_STYLE.Flow };
  return { title: nt ? `${nt.name}${nt.disabled ? ' (disabled)' : ''}` : 'Step', icon: iconFor(nt?.icon), style: CATEGORY_STYLE[nt?.category] || CATEGORY_STYLE.Flow };
}

function handlesOf(node) {
  if (node.type === 'condition') return ['true', 'false'];
  if (node.type === 'switch') return [...(node.data?.cases || []).filter((c) => String(c).trim()), 'default'];
  return [null];
}

function StepNode({ id, data, type, selected }) {
  const m = data._meta || {};
  const Icon = m.icon || Play;
  const StatusIcon = STATUS_ICON[data._status];
  const cases = type === 'switch' ? [...(data.cases || []).filter((c) => String(c).trim()), 'default'] : [];
  // Switch handles change with the path names: tell React Flow so connections are redrawn.
  const updateInternals = useUpdateNodeInternals();
  const handleKey = cases.join('|');
  useEffect(() => {
    if (type === 'switch') updateInternals(id);
  }, [handleKey, id, type, updateInternals]);
  return (
    <div className={cx('w-56 rounded-lg border-2 bg-surface px-3 py-2 shadow-card', selected ? m.style?.border : 'border-line')}>
      {type !== 'input' && <Handle type="target" position={Position.Top} />}
      <div className="flex items-center gap-2">
        <div className={cx('rounded-md p-1.5', m.style?.bg)}>
          <Icon className={cx('h-4 w-4', m.style?.text)} />
        </div>
        <div className="min-w-0 flex-1">
          <div className={cx('truncate text-[10px] font-semibold uppercase tracking-wide', m.style?.text)}>{m.title}</div>
          <div className="truncate text-sm text-ink">{data.label || m.title}</div>
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
            <Handle key={`${i}-${c}`} type="source" position={Position.Bottom} id={c} style={{ left: `${((i + 1) * 100) / (cases.length + 1)}%`, background: c === 'default' ? 'rgb(var(--muted))' : 'rgb(var(--navy-500))' }} />
          ))}
          <div className="mt-1 flex justify-around text-[10px] font-semibold text-slate-700">
            {cases.map((c, i) => <span key={`${i}-${c}`} className="max-w-[4rem] truncate">{c}</span>)}
          </div>
        </>
      )}
      {type !== 'end' && !BRANCHING.includes(type) && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

function DeletableEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, selected, markerEnd, style, data }) {
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ ...style, strokeWidth: selected ? 2.5 : 1.5, stroke: selected ? 'rgb(var(--brand-600))' : 'rgb(var(--navy-300))' }} />
      <EdgeLabelRenderer>
        <div style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: 'all' }} className="nodrag nopan flex items-center gap-1">
          {label && <span className="rounded bg-surface px-1 text-[10px] font-medium text-muted-strong shadow-sm">{label}</span>}
          {selected && data?.onDelete && (
            <button type="button" title="Remove this connection" aria-label="Remove this connection" onClick={() => data.onDelete(id)} className="rounded-full border bg-surface p-0.5 text-muted-strong shadow hover:text-red-600">
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = Object.fromEntries(['input', 'action', 'loop', 'condition', 'switch', 'end', 'agent', 'tool', 'transform'].map((t) => [t, StepNode]));
const edgeTypes = { step: DeletableEdge };

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

function edgeLabel(handle) {
  if (!handle) return undefined;
  return handle === 'true' ? 'Yes' : handle === 'false' ? 'No' : handle;
}

function clean(nodes, edges) {
  return {
    nodes: nodes.map(({ id, type, position, data }) => ({ id, type, position, data })),
    edges: edges.map(({ id, source, target, sourceHandle, label }) => ({ id, source, target, sourceHandle: sourceHandle || null, label: label || null })),
  };
}

/** Replace {{input.old...}} with {{input.new...}} everywhere in a node's data. */
function renameRefs(value, from, to) {
  if (typeof value === 'string') return value.replace(new RegExp(`(\\{\\{\\s*input\\.)${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?=[.\\s}])`, 'g'), `$1${to}`);
  if (Array.isArray(value)) return value.map((v) => renameRefs(v, from, to));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, renameRefs(v, from, to)]));
  return value;
}

const draftKey = (userId, id) => `agentos.unsaved.${userId}.${id ?? 'new'}`;

export default function FlowBuilder({ workflow, draft, catalog, credentialTypes, agents, user, onBack, onSaved, onOpenVersion }) {
  const initial = draft?.definition || (workflow?.definition?.nodes?.length ? workflow.definition : blank());
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges.map((e) => ({ ...e, type: 'step', label: e.label || edgeLabel(e.sourceHandle) })));
  const [current, setCurrent] = useState(workflow);
  const [versions, setVersions] = useState([]);
  const [name, setName] = useState(draft?.name || workflow?.name || 'New workflow');
  const [meta_, setMeta] = useState({
    description: draft?.description || workflow?.description || '',
    trigger_keywords: workflow?.trigger_keywords || '',
    visibility: workflow?.visibility || 'private',
  });
  const [flowSettings, setFlowSettings] = useState(initial.settings || {});
  const [selectedId, setSelectedId] = useState(null);
  const [notice, setNotice] = useState(draft?.warnings?.length ? { kind: 'info', text: `Drafted by AI. Still to do: ${draft.warnings.join(' • ')}` } : null);
  const [busy, setBusy] = useState('');
  const [dirty, setDirtyState] = useState(!!draft);
  const [testOpen, setTestOpen] = useState(false);
  const [triggersOpen, setTriggersOpen] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [paletteQuery, setPaletteQuery] = useState('');
  const [restore, setRestore] = useState(null);
  const [history, setHistory] = useState({ undo: [], redo: [] });
  const lastSnap = useRef(0);
  const draftKeys = useRef(new Set());
  const setGlobalDirty = useUnsaved((s) => s.setDirty);

  const editable = !current || current.can_edit;
  const isDraft = !current || current.status === 'draft';
  const live = versions.find((v) => v.status === 'active');
  const selected = nodes.find((n) => n.id === selectedId);
  const startNode = nodes.find((n) => n.type === 'input');
  const stepResults = useMemo(() => Object.fromEntries((lastRun?.steps || []).map((s) => [s.node_id, s])), [lastRun]);

  const setDirty = useCallback((v) => {
    setDirtyState(v);
    setGlobalDirty(v);
  }, [setGlobalDirty]);

  // ---------- versions, unsaved-work protection ----------
  const loadVersions = useCallback((groupId) => {
    if (groupId) api.get('/workflows', { params: { group_id: groupId } }).then((r) => setVersions(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    loadVersions(current?.group_id);
  }, [current?.group_id, current?.status, loadVersions]);

  useEffect(() => {
    if (current?.id) window.history.replaceState(null, '', `#/workflows/${current.id}`);
  }, [current?.id]);

  useEffect(() => {
    const onUnload = (e) => {
      if (useUnsaved.getState().dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onUnload);
    const keys = draftKeys.current;
    return () => {
      window.removeEventListener('beforeunload', onUnload);
      setGlobalDirty(false);
      try {
        for (const k of keys) localStorage.removeItem(k);
      } catch {
        /* ignore */
      }
    };
  }, [setGlobalDirty]);

  // Offer to restore work left unsaved (refresh, expired session, closed tab).
  useEffect(() => {
    if (draft) return;
    try {
      const saved = JSON.parse(localStorage.getItem(draftKey(user.id, workflow?.id)) || 'null');
      if (saved) setTimeout(() => setRestore(saved), 0);
    } catch {
      /* ignore */
    }
  }, [workflow?.id, draft, user.id]);

  useEffect(() => {
    if (!dirty) return undefined;
    const t = setTimeout(() => {
      try {
        draftKeys.current.add(draftKey(user.id, current?.id ?? workflow?.id));
        localStorage.setItem(draftKey(user.id, current?.id ?? workflow?.id), JSON.stringify({ name, meta: meta_, settings: flowSettings, definition: clean(nodes, edges), at: Date.now() }));
      } catch {
        /* storage full or unavailable */
      }
    }, 800);
    return () => clearTimeout(t);
  }, [dirty, nodes, edges, name, meta_, flowSettings, current?.id, workflow?.id, user.id]);

  // ---------- undo / redo ----------
  const snapshot = useCallback((throttle = false) => {
    const now = Date.now();
    if (throttle && now - lastSnap.current < 1000) return;
    lastSnap.current = now;
    const snap = clean(nodes, edges);
    setHistory((h) => ({ undo: [...h.undo.slice(-49), snap], redo: [] }));
  }, [nodes, edges]);

  const applySnap = (snap) => {
    setNodes(snap.nodes);
    setEdges(snap.edges.map((e) => ({ ...e, type: 'step' })));
    setDirty(true);
  };
  const undo = () => {
    if (!history.undo.length) return;
    const prev = history.undo[history.undo.length - 1];
    setHistory((h) => ({ undo: h.undo.slice(0, -1), redo: [...h.redo, clean(nodes, edges)] }));
    applySnap(prev);
  };
  const redo = () => {
    if (!history.redo.length) return;
    const next = history.redo[history.redo.length - 1];
    setHistory((h) => ({ undo: [...h.undo, clean(nodes, edges)], redo: h.redo.slice(0, -1) }));
    applySnap(next);
  };

  // ---------- editing ----------
  const removeEdge = useCallback((id) => {
    snapshot();
    setDirty(true);
    setEdges((eds) => eds.filter((e) => e.id !== id));
  }, [snapshot, setDirty, setEdges]);

  const viewNodes = useMemo(
    () => nodes.map((n) => ({ ...n, deletable: false, data: { ...n.data, _meta: meta(n, catalog), _status: stepResults[n.id]?.status } })),
    [nodes, catalog, stepResults],
  );
  const viewEdges = useMemo(() => edges.map((e) => ({ ...e, type: 'step', deletable: false, data: { onDelete: editable ? removeEdge : null } })), [edges, editable, removeEdge]);

  const onNodesChangeSafe = (changes) => {
    const real = changes.filter((c) => c.type !== 'remove');
    if (real.some((c) => c.type === 'position' && c.dragging) && !dirty) setDirty(true);
    onNodesChange(real);
  };
  const onEdgesChangeSafe = (changes) => onEdgesChange(changes.filter((c) => c.type !== 'remove'));

  const onConnect = (params) => {
    snapshot();
    setDirty(true);
    const sourceIsBranch = BRANCHING.includes(nodes.find((n) => n.id === params.source)?.type);
    // A branch handle leads to one place: connecting it again replaces the old connection.
    setEdges((eds) => addEdge(
      { ...params, type: 'step', label: edgeLabel(params.sourceHandle) },
      eds.filter((e) => !(sourceIsBranch && e.source === params.source && (e.sourceHandle || null) === (params.sourceHandle || null))),
    ));
  };

  const updateData = (id, patch) => {
    snapshot(true);
    setDirty(true);
    setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
  };

  const newNodeData = (type, action) => {
    const nt = catalog.find((n) => n.key === action);
    if (type === 'action') return { label: nt?.name || 'Step', action, config: {}, settings: {} };
    if (type === 'condition') return { label: 'Check', condition: { left: '', operator: '==', right: '' } };
    if (type === 'switch') return { label: 'Route', value: '', cases: ['option 1', 'option 2'] };
    if (type === 'loop') return { label: 'Repeat for each', items: '', action: '', config: {} };
    return { label: 'Finish' };
  };

  /** Add a step where a non-coder expects it: after the selected step, on a free branch, or before Finish. */
  const addStep = (type, action) => {
    snapshot();
    setDirty(true);
    const id = newId();
    const data = newNodeData(type, action);
    let anchor = selected;
    if (!anchor || anchor.type === 'end') {
      const finish = anchor?.type === 'end' ? anchor : null;
      const intoFinish = edges.filter((e) => nodes.find((n) => n.id === e.target)?.type === 'end' && (!finish || e.target === finish.id));
      const plain = intoFinish.filter((e) => !BRANCHING.includes(nodes.find((n) => n.id === e.source)?.type));
      anchor = plain.length === 1 ? nodes.find((n) => n.id === plain[0].source) : null;
    }
    if (!anchor) {
      const maxY = Math.max(...nodes.map((n) => n.position.y), 0);
      setNodes((nds) => [...nds, { id, type, position: { x: 620, y: maxY }, data }]);
      setSelectedId(id);
      setNotice({ kind: 'info', text: "Step added on the right. Drag from a step's bottom dot to the next step's top dot to connect it." });
      return;
    }
    if (BRANCHING.includes(anchor.type)) {
      const handles = handlesOf(anchor);
      const used = new Set(edges.filter((e) => e.source === anchor.id).map((e) => e.sourceHandle || null));
      const free = handles.findIndex((h) => !used.has(h));
      const h = free === -1 ? null : handles[free];
      const x = anchor.position.x + (free === -1 ? 320 + (nodes.length % 3) * 40 : (free - (handles.length - 1) / 2) * 260);
      setNodes((nds) => [...nds, { id, type, position: { x, y: anchor.position.y + 140 }, data }]);
      if (free === -1) setNotice({ kind: 'info', text: `Every path of “${anchor.data?.label}” is already connected, so the new step was placed on the right. Connect it where it belongs (click a connection and × to remove one).` });
      // A new branch also leads on to Finish (when there is just one), so the path is complete.
      const finishes = nodes.filter((n) => n.type === 'end');
      const onward = type !== 'end' && !BRANCHING.includes(type) && finishes.length === 1
        ? [{ id: `e-${id}-${finishes[0].id}`, source: id, target: finishes[0].id, type: 'step' }] : [];
      if (h !== null) setEdges((eds) => [...eds, { id: `e-${anchor.id}-${id}`, source: anchor.id, sourceHandle: h, target: id, type: 'step', label: edgeLabel(h) }, ...onward]);
      setSelectedId(id);
      return;
    }
    const position = { x: anchor.position.x, y: anchor.position.y + 130 };
    setNodes((nds) => [...nds.map((n) => (n.position.y > anchor.position.y ? { ...n, position: { ...n.position, y: n.position.y + 130 } } : n)), { id, type, position, data }]);
    setEdges((eds) => {
      const outgoing = eds.filter((e) => e.source === anchor.id);
      const rest = eds.filter((e) => e.source !== anchor.id);
      const firstHandle = type === 'condition' ? 'true' : type === 'switch' ? 'default' : null;
      let moved = type === 'end' ? [] : outgoing.map((e) => ({ ...e, id: `e-${id}-${e.target}`, source: id, sourceHandle: firstHandle, label: edgeLabel(firstHandle) }));
      const finishes = nodes.filter((n) => n.type === 'end');
      if (!moved.length && type !== 'end' && finishes.length === 1) {
        moved = [{ id: `e-${id}-${finishes[0].id}`, source: id, sourceHandle: firstHandle, target: finishes[0].id, type: 'step', label: edgeLabel(firstHandle) }];
      }
      return [...rest, { id: `e-${anchor.id}-${id}`, source: anchor.id, target: id, type: 'step' }, ...moved];
    });
    setSelectedId(id);
  };

  const removeNode = (nodeId) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node || node.type === 'input') return;
    snapshot();
    setDirty(true);
    const incoming = edges.filter((e) => e.target === nodeId);
    const outgoing = edges.filter((e) => e.source === nodeId);
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => {
      const kept = eds.filter((e) => e.source !== nodeId && e.target !== nodeId);
      if (incoming.length === 1 && outgoing.length === 1 && !BRANCHING.includes(node.type)) {
        kept.push({ ...incoming[0], id: `e-${incoming[0].source}-${outgoing[0].target}`, target: outgoing[0].target });
      }
      return kept;
    });
    setSelectedId(null);
  };

  const renameCase = (nodeId, from, to) => setEdges((eds) => eds.map((e) => (e.source === nodeId && e.sourceHandle === from ? { ...e, sourceHandle: to, label: edgeLabel(to) } : e)));
  const dropCase = (nodeId, value) => setEdges((eds) => eds.filter((e) => !(e.source === nodeId && e.sourceHandle === value)));
  const renameField = (from, to) => {
    if (!from || from === to) return;
    setNodes((nds) => nds.map((n) => (n.type === 'input' ? n : { ...n, data: renameRefs(n.data, from, to) })));
  };

  // Keyboard: Delete/Backspace removes the selected connection or step (never Start); Ctrl/Cmd+Z undoes.
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target?.tagName || '').toLowerCase();
      if (['input', 'textarea', 'select'].includes(tag) || e.target?.isContentEditable || !editable) return;
      if (document.querySelector('[role=dialog]')) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        const edge = edges.find((ed) => ed.selected);
        if (edge) removeEdge(edge.id);
        else if (selected && selected.type !== 'input') removeNode(selected.id);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // ---------- saving & lifecycle ----------
  const body = () => ({
    name: name.trim() || 'Untitled workflow',
    description: meta_.description || null,
    trigger_keywords: meta_.trigger_keywords || null,
    visibility: meta_.visibility,
    definition: { ...clean(nodes, edges), settings: flowSettings },
  });

  const save = async () => {
    setBusy('save');
    try {
      const saved = current && isDraft ? (await api.put(`/workflows/${current.id}`, body())).data : (await api.post('/workflows', { ...body(), group_id: current?.group_id })).data;
      const newVersion = current && saved.id !== current.id;
      try {
        localStorage.removeItem(draftKey(user.id, current?.id ?? workflow?.id));
      } catch {
        /* ignore */
      }
      setCurrent(saved);
      setDirty(false);
      onSaved?.();
      loadVersions(saved.group_id);
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
    if (!res.is_valid) setNotice({ kind: 'error', text: res.errors.join(' • ') });
    else if (res.warnings?.length) setNotice({ kind: 'info', text: `Looks good. Note: ${res.warnings.join(' • ')}` });
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

  const turnOff = async () => {
    if (!live || !confirm('Turn this workflow off? Schedules, webhooks, form links and chat will stop starting it.')) return;
    try {
      const res = (await api.post(`/workflows/${live.id}/deactivate`)).data;
      if (res.id === current?.id) setCurrent(res);
      loadVersions(res.group_id);
      onSaved?.();
      setNotice({ kind: 'info', text: 'Turned off. Use Turn on (or Publish) to start it again.' });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    }
  };

  const fallbackVersion = live || [...versions].filter((v) => v.id !== current?.id).sort((a, b) => b.version - a.version)[0];
  const newerDraft = current && current.status !== 'draft' ? versions.find((v) => v.status === 'draft' && v.version > current.version) : null;
  const discardDraft = async () => {
    if (!current || current.status !== 'draft' || !fallbackVersion || !confirm(`Discard this draft and go back to version ${fallbackVersion.version}?`)) return;
    await api.delete(`/workflows/${current.id}`);
    setDirty(false);
    onSaved?.();
    onOpenVersion?.(fallbackVersion);
  };

  const openTest = async () => {
    const wf = await ensureSaved();
    if (wf) setTestOpen(true);
  };

  const doRestore = () => {
    snapshot();
    setNodes(restore.definition.nodes);
    setEdges(restore.definition.edges.map((e) => ({ ...e, type: 'step' })));
    setName(restore.name);
    setMeta(restore.meta);
    setFlowSettings(restore.settings || {});
    setDirty(true);
    setRestore(null);
  };
  const dropRestore = () => {
    try {
      localStorage.removeItem(draftKey(user.id, workflow?.id));
    } catch {
      /* ignore */
    }
    setRestore(null);
  };

  const groups = selected ? availableVariables(selected.id, nodes, edges, catalog, agents) : [];
  const q = paletteQuery.trim().toLowerCase();
  const palette = catalog.filter((n) => !n.disabled && (!q || `${n.name} ${n.description}`.toLowerCase().includes(q)));
  const anchorHint = selected && selected.type !== 'end' ? `after “${selected.data?.label}”` : 'before Finish';
  const statusLabel = !current ? 'draft' : current.status === 'active' ? 'live' : current.status === 'archived' ? (live ? 'old version' : 'off') : 'draft';

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b bg-surface px-4 py-2.5">
        <Button variant="ghost" icon={ArrowLeft} onClick={() => { if (!dirty || confirm('Leave without saving?')) { setDirty(false); onBack(); } }}>Back</Button>
        <Input className="max-w-xs font-medium" value={name} disabled={!editable} maxLength={200} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        {versions.length > 1 ? (
          <select
            aria-label="Version"
            className="rounded-md border px-2 py-1 text-xs"
            value={current?.id}
            onChange={(e) => {
              const v = versions.find((x) => x.id === Number(e.target.value));
              if (v && (!dirty || confirm('Open another version without saving?'))) { setDirty(false); onOpenVersion?.(v); }
            }}
          >
            {versions.map((v) => <option key={v.id} value={v.id}>v{v.version} · {v.status === 'active' ? 'live' : v.status === 'archived' ? 'old' : 'draft'}</option>)}
          </select>
        ) : (
          current && <span className="text-xs text-muted-strong">v{current.version}</span>
        )}
        <StatusBadge status={statusLabel} />
        {dirty && <span className="text-xs text-amber-600">unsaved changes</span>}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {editable && (
            <>
              <button title="Undo (Ctrl+Z)" aria-label="Undo" onClick={undo} disabled={!history.undo.length} className="rounded p-1.5 text-muted-strong hover:bg-brand-50 disabled:opacity-30"><Undo2 className="h-4 w-4" /></button>
              <button title="Redo (Ctrl+Shift+Z)" aria-label="Redo" onClick={redo} disabled={!history.redo.length} className="rounded p-1.5 text-muted-strong hover:bg-brand-50 disabled:opacity-30"><Redo2 className="h-4 w-4" /></button>
              <Button variant="secondary" icon={Save} loading={busy === 'save'} onClick={save}>Save</Button>
              <Button variant="secondary" icon={FlaskConical} onClick={openTest}>Test</Button>
            </>
          )}
          {current && editable && can(user, 'trigger:write') && <Button variant="secondary" icon={Clock} onClick={() => setTriggersOpen(true)}>How it starts</Button>}
          {editable && current?.status === 'draft' && fallbackVersion && <Button variant="ghost" onClick={discardDraft}>Discard draft</Button>}
          {editable && can(user, 'workflow:activate') && live && (current?.id !== live.id || !dirty) && <Button variant="secondary" icon={Power} onClick={turnOff}>Turn off</Button>}
          {editable && can(user, 'workflow:activate') && (current?.status !== 'active' || dirty) && (
            <Button icon={Rocket} loading={busy === 'publish'} onClick={publish}>{statusLabel === 'off' && !dirty ? 'Turn on' : 'Publish'}</Button>
          )}
        </div>
      </div>
      {newerDraft && (
        <div className="flex flex-wrap items-center gap-2 border-b bg-brand-50 px-4 py-2 text-sm text-brand-800">
          You are looking at version {current.version}. There is a newer draft (version {newerDraft.version}); saving here would start yet another draft.
          <Button variant="secondary" onClick={() => { if (!dirty || confirm('Open the draft without saving?')) { setDirty(false); onOpenVersion?.(newerDraft); } }}>Open the draft</Button>
        </div>
      )}
      {restore && (
        <div className="flex flex-wrap items-center gap-2 border-b bg-amber-50 px-4 py-2 text-sm text-amber-900">
          You have unsaved changes from {new Date(restore.at).toLocaleString()}.
          <Button variant="secondary" onClick={doRestore}>Restore them</Button>
          <Button variant="ghost" onClick={dropRestore}>Discard</Button>
        </div>
      )}
      {notice && (
        <div className="flex items-start gap-2 border-b bg-surface px-4 py-2">
          <div className="flex-1"><Alert kind={notice.kind}>{notice.text}</Alert></div>
          <button onClick={() => setNotice(null)} className="p-1 text-muted hover:text-ink" aria-label="Dismiss"><X className="h-4 w-4" /></button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {editable && (
          <div className="flex w-60 flex-shrink-0 flex-col border-r bg-surface">
            <div className="p-3 pb-2">
              <div className="mb-2 text-xs font-semibold uppercase text-muted-strong">Add a step</div>
              <div className="relative">
                <Search className="absolute left-2 top-2 h-4 w-4 text-muted" />
                <input className="w-full rounded-md border py-1.5 pl-7 pr-2 text-sm placeholder:text-muted focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/20" placeholder="Search steps" value={paletteQuery} onChange={(e) => setPaletteQuery(e.target.value)} />
              </div>
              <p className="mt-2 text-xs text-muted-strong">New steps go {anchorHint}.</p>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-3 pb-3">
              {['AI', 'Apps', 'Data', 'Flow'].map((cat) => {
                const items = palette.filter((n) => n.category === cat);
                const logic = cat === 'Flow' ? LOGIC.filter((l) => !q || `${l.name} ${l.description}`.toLowerCase().includes(q)) : [];
                if (!items.length && !logic.length) return null;
                const st = CATEGORY_STYLE[cat];
                return (
                  <div key={cat}>
                    <div className={cx('mb-1 text-[11px] font-semibold uppercase', st.text)}>{cat === 'Flow' ? 'Logic & flow' : cat}</div>
                    {[...logic.map((l) => ({ ...l, onClick: () => addStep(l.type), Icon: l.icon, key: l.type })),
                      ...items.map((n) => ({ ...n, onClick: () => addStep('action', n.key), Icon: iconFor(n.icon) }))].map((it) => (
                      <button key={it.key} onClick={it.onClick} title={it.description} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-brand-50">
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
            edges={viewEdges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={editable ? onNodesChangeSafe : undefined}
            onEdgesChange={editable ? onEdgesChangeSafe : undefined}
            onConnect={editable ? onConnect : undefined}
            onNodeDragStart={() => editable && snapshot()}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            nodesDraggable={editable}
            nodesConnectable={editable}
            deleteKeyCode={null}
            fitView
            fitViewOptions={{ maxZoom: 1 }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <div className="w-96 flex-shrink-0 overflow-y-auto border-l bg-surface p-4">
          {selected ? (
            <fieldset disabled={!editable} className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-navy">{meta(selected, catalog).title}</h3>
                {editable && selected.type !== 'input' && <Button variant="danger" icon={Trash2} onClick={() => removeNode(selected.id)}>Remove</Button>}
              </div>
              {selected.type === 'action' && <p className="-mt-2 text-sm text-muted-strong">{catalog.find((n) => n.key === selected.data?.action)?.description}</p>}
              <Field label="Name of this step">
                <Input value={selected.data?.label || ''} maxLength={120} onChange={(e) => updateData(selected.id, { label: e.target.value })} />
              </Field>
              <NodeSettings
                node={selected}
                catalog={catalog}
                groups={groups}
                agents={agents}
                credentialTypes={credentialTypes}
                onChange={(patch) => updateData(selected.id, patch)}
                onTriggers={current && editable ? () => setTriggersOpen(true) : null}
                onRenameCase={(from, to) => renameCase(selected.id, from, to)}
                onDropCase={(v) => dropCase(selected.id, v)}
                onRenameField={renameField}
              />
              {stepResults[selected.id] && <StepResult step={stepResults[selected.id]} />}
            </fieldset>
          ) : (
            <AutomationSettings meta={meta_} setMeta={(m) => { setMeta(m); setDirty(true); }} settings={flowSettings} setSettings={(s) => { setFlowSettings(s); setDirty(true); }} editable={editable} lastRun={lastRun} credentialTypes={credentialTypes} />
          )}
        </div>
      </div>

      {testOpen && current && (
        <TestRun workflow={current} fields={startNode?.data?.fields || []} onClose={() => setTestOpen(false)} onResult={(run) => { setLastRun(run); setNotice(run.status === 'succeeded' ? { kind: 'success', text: 'Test succeeded. Click a step to see what it produced.' } : { kind: 'error', text: run.error }); }} />
      )}
      {triggersOpen && current && <Triggers workflow={current} isLive={!!live} fields={startNode?.data?.fields || []} onClose={() => setTriggersOpen(false)} />}
    </div>
  );
}

function StepResult({ step }) {
  return (
    <div className="rounded-md border bg-app p-3">
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-muted-strong">
        Last test <StatusBadge status={step.status === 'success' ? 'succeeded' : step.status} />
        {step.attempts > 1 && <span className="normal-case">{step.attempts} attempts</span>}
      </div>
      {step.error && <p className="mb-1 text-sm text-red-600">{step.error}</p>}
      {step.output !== undefined && <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs text-ink">{JSON.stringify(step.output, null, 2)}</pre>}
    </div>
  );
}

function AlertSettings({ settings, setSettings, credentialTypes }) {
  const [creds, setCreds] = useState([]);
  useEffect(() => {
    api.get('/credentials', { params: { type: 'slack_webhook|teams_webhook|smtp' } }).then((r) => setCreds(r.data)).catch(() => {});
  }, []);
  const notify = settings.notify_on_failure || {};
  const chosen = creds.find((c) => c.id === Number(notify.credential_id));
  const set = (patch) => setSettings({ ...settings, notify_on_failure: { ...notify, ...patch } });
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="text-sm font-medium text-ink">Tell me when it fails</div>
      <Select aria-label="Failure alerts" value={notify.credential_id || ''} onChange={(e) => set({ credential_id: e.target.value ? Number(e.target.value) : '' })}>
        <option value="">Don't send alerts</option>
        {notify.credential_id && !chosen && <option value={notify.credential_id}>Set by the owner (not shared with you)</option>}
        {creds.map((c) => <option key={c.id} value={c.id}>{credentialTypes.find((t) => t.key === c.type)?.name || c.type}: {c.name}</option>)}
      </Select>
      {chosen?.type === 'smtp' && <Input type="email" placeholder="Email address to alert" value={notify.email_to || ''} onChange={(e) => set({ email_to: e.target.value })} />}
      <p className="text-xs text-muted-strong">Sent when a scheduled, webhook, form or chat run fails (not for tests). Add Slack, Teams or email under Connections.</p>
    </div>
  );
}

function AutomationSettings({ meta, setMeta, settings, setSettings, editable, lastRun, credentialTypes }) {
  return (
    <fieldset disabled={!editable} className="space-y-3">
      <h3 className="font-semibold text-navy">About this workflow</h3>
      <Field label="Description">
        <Textarea rows={3} className="font-sans" maxLength={2000} value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} />
      </Field>
      <Field label="Who can run it">
        <Select value={meta.visibility} onChange={(e) => setMeta({ ...meta, visibility: e.target.value })}>
          <option value="private">Only me</option>
          <option value="department">My department</option>
          <option value="public">Everyone</option>
        </Select>
      </Field>
      <AlertSettings settings={settings} setSettings={setSettings} credentialTypes={credentialTypes} />
      <details className="rounded-md border p-2 text-sm">
        <summary className="cursor-pointer text-muted-strong">Advanced</summary>
        <div className="mt-2">
          <Field label="Chat keywords" hint="Comma separated. Chat messages containing one run this workflow directly (otherwise the AI decides).">
            <Input value={meta.trigger_keywords} onChange={(e) => setMeta({ ...meta, trigger_keywords: e.target.value })} />
          </Field>
        </div>
      </details>
      <div className="rounded-md bg-brand-50 p-3 text-sm text-brand-900">
        <b>Tips</b>
        <ul className="mt-1 list-disc space-y-1 pl-4">
          <li>Click a step to set it up. Use <i>Insert data</i> to use results from earlier steps.</li>
          <li>New steps are added after the selected step (or before Finish). Click a connection to remove it.</li>
          <li><b>Test</b> runs your draft; <b>Publish</b> makes it live. Ctrl+Z undoes.</li>
        </ul>
      </div>
      {lastRun && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-muted-strong">Last test result</div>
          {lastRun.status === 'succeeded' ? <ResultView value={lastRun.output?.result} /> : <Alert>{lastRun.error}</Alert>}
        </div>
      )}
    </fieldset>
  );
}

function NodeSettings({ node, catalog, groups, agents, credentialTypes, onChange, onTriggers, onRenameCase, onDropCase, onRenameField }) {
  const data = node.data || {};
  const [caseError, setCaseError] = useState('');

  if (node.type === 'input') {
    const fields = data.fields || [];
    const setFields = (f) => onChange({ fields: f });
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-strong">A workflow starts when someone fills in this form, from chat, a public form link, a schedule or a webhook.</p>
        {onTriggers && <Button variant="secondary" icon={Clock} onClick={onTriggers}>Schedule, form link or webhook</Button>}
        <div className="text-xs font-semibold uppercase text-muted-strong">Form fields</div>
        {!fields.length && <p className="text-xs text-muted-strong">No fields yet. Add some so people can give the workflow information.</p>}
        {fields.map((f, i) => (
          <div key={i} className="space-y-1.5 rounded-md border bg-app p-2">
            <div className="flex gap-1">
              <Input placeholder="Label" value={f.label} maxLength={100} onChange={(e) => {
                const label = e.target.value;
                const base = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || `field_${i + 1}`;
                const key = fields.some((x, j) => j !== i && x.key === base) ? `${base}_${i + 1}` : base;
                onRenameField(f.key, key);
                setFields(fields.map((x, j) => (j === i ? { ...x, label, key } : x)));
              }} />
              <button type="button" className="p-1 text-muted hover:text-red-600" onClick={() => setFields(fields.filter((_, j) => j !== i))} aria-label="Remove field"><X className="h-4 w-4" /></button>
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
            <p className="font-mono text-[11px] text-muted-strong">{`{{input.${f.key}}}`}</p>
          </div>
        ))}
        <Button variant="secondary" icon={Plus} onClick={() => setFields([...fields, { key: `field_${fields.length + 1}`, label: '', type: 'text', required: false }])}>Add field</Button>
      </div>
    );
  }

  if (node.type === 'action' || node.type === 'loop') {
    const isLoop = node.type === 'loop';
    const nt = catalog.find((n) => n.key === data.action);
    const settings = data.settings || {};
    const loopGroups = isLoop ? [{ label: 'Current item', root: 'item', vars: [{ label: 'item', value: '{{item}}' }, { label: 'position (1, 2, 3…)', value: '{{index}}' }] }, ...groups] : groups;
    return (
      <div className="space-y-4">
        {isLoop && (
          <>
            <Field label="List to go through *" hint="A list from an earlier step (e.g. Text tools → split), or one item per line.">
              <VarText value={data.items || ''} groups={groups} placeholder="{{split.result}}" onChange={(v) => onChange({ items: v })} />
            </Field>
            <Field label="For each item, do">
              <Select value={data.action || ''} onChange={(e) => onChange({ action: e.target.value, config: {} })}>
                <option value="">Choose a step…</option>
                {catalog.filter((n) => !n.disabled).map((n) => <option key={n.key} value={n.key}>{n.name}</option>)}
              </Select>
            </Field>
          </>
        )}
        {!nt && !isLoop && <Alert>This step type is not available (it may have been disabled by an administrator).</Alert>}
        {nt?.disabled && <Alert>{nt.name} steps are disabled by your administrator. This workflow will fail until the step is replaced.</Alert>}
        {nt && <StepForm nodeType={nt} config={data.config || {}} onChange={(config) => onChange({ config })} groups={loopGroups} agents={agents} credentialTypes={credentialTypes} />}
        {nt && (
          <details className="rounded-md border p-2 text-sm">
            <summary className="cursor-pointer text-muted-strong">If this step fails…</summary>
            <div className="mt-2 space-y-2">
              {isLoop ? (
                <Checkbox label="If one item fails, keep going with the others" checked={!!settings.item_errors_continue} onChange={(e) => onChange({ settings: { ...settings, item_errors_continue: e.target.checked } })} />
              ) : (
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
              )}
              <Checkbox label="Keep the workflow going (the step's output becomes { error })" checked={!!settings.continue_on_error} onChange={(e) => onChange({ settings: { ...settings, continue_on_error: e.target.checked } })} />
            </div>
          </details>
        )}
        {nt?.output_hint && <p className="text-xs text-muted-strong">Produces: <code>{isLoop ? '{ results: [...], count }' : nt.output_hint}</code></p>}
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
        <p className="text-xs text-muted-strong">Connect the green <b>Yes</b> and red <b>No</b> dots to the next steps (selecting this step and adding a new one does it for you).</p>
      </div>
    );
  }

  if (node.type === 'switch') {
    const cases = data.cases || [];
    const clash = (value, index) => {
      const v = value.trim().toLowerCase();
      return v === 'default' || cases.some((x, j) => j !== index && String(x).trim().toLowerCase() === v);
    };
    return (
      <div className="space-y-3">
        <Field label="Route by this value"><VarText value={data.value || ''} groups={groups} placeholder="{{classify.category}}" onChange={(v) => onChange({ value: v })} /></Field>
        <div className="text-xs font-semibold uppercase text-muted-strong">Paths</div>
        {cases.map((c, i) => (
          <div key={i} className="flex gap-1">
            <Input value={c} maxLength={60} onChange={(e) => {
              const v = e.target.value;
              if (clash(v, i)) {
                setCaseError(v.trim().toLowerCase() === 'default' ? "'default' is reserved for everything else" : 'Each path needs a different name');
                return;
              }
              setCaseError('');
              onRenameCase(c, v);
              onChange({ cases: cases.map((x, j) => (j === i ? v : x)) });
            }} />
            <button type="button" className="p-1 text-muted hover:text-red-600" onClick={() => { onDropCase(c); onChange({ cases: cases.filter((_, j) => j !== i) }); }} aria-label="Remove path"><X className="h-4 w-4" /></button>
          </div>
        ))}
        {caseError && <p className="text-xs text-red-600">{caseError}</p>}
        <Button variant="secondary" icon={Plus} onClick={() => {
          let n = cases.length + 1;
          while (clash(`option ${n}`, -1)) n += 1;
          onChange({ cases: [...cases, `option ${n}`] });
        }}>Add path</Button>
        <p className="text-xs text-muted-strong">Each path gets its own dot under the step; anything else goes to <b>default</b>. Matching ignores upper/lower case.</p>
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

  return <p className="text-sm text-muted-strong">This is an older step type. It still runs, but cannot be edited here.</p>;
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
