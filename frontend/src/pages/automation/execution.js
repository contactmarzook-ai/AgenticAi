// Non-component helpers for the builder's validation and execution panels (kept apart from the
// component files so fast refresh keeps working).
import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../lib/api';

// ---------- live validation ----------

/** What counts as a change worth re-checking: everything except where the steps sit on the canvas. */
function contentKey(definition) {
  return JSON.stringify({
    nodes: (definition.nodes || []).map(({ id, type, data }) => ({ id, type, data })),
    edges: definition.edges,
    settings: definition.settings,
  });
}

const IDLE = { status: 'idle', errors: [], warnings: [] };

/**
 * Checks the canvas as you edit (debounced), without saving. Dragging steps around does not
 * trigger a request; only changes to steps, connections or settings do.
 * Returns { status: 'idle'|'checking'|'done'|'unavailable', errors, warnings }.
 */
export function useLiveValidation(definition, workflowId, enabled, delay = 600) {
  const key = useMemo(() => contentKey(definition), [definition]);
  const latest = useRef(definition);
  const [result, setResult] = useState(IDLE);

  useEffect(() => {
    latest.current = definition;
  }, [definition]);

  useEffect(() => {
    if (!enabled) return undefined;
    let stale = false;
    const t = setTimeout(async () => {
      setResult((r) => ({ ...r, status: 'checking' }));
      try {
        const body = { definition: latest.current };
        if (workflowId) body.workflow_id = workflowId;
        const res = (await api.post('/workflows/validate-definition', body)).data;
        if (!stale) setResult({ status: 'done', errors: res.errors || [], warnings: res.warnings || [] });
      } catch {
        if (!stale) setResult({ status: 'unavailable', errors: [], warnings: [] });
      }
    }, delay);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [key, workflowId, enabled, delay]);

  return enabled ? result : IDLE;
}

/** Which steps a message is about: messages start with (or quote) the step's name, e.g. 'Send email': fill in 'To'. */
export function nodesMentioned(message, nodes) {
  const named = nodes
    .map((n) => ({ id: n.id, label: n.data?.label || n.type }))
    .filter((n) => n.label)
    .sort((a, b) => b.label.length - a.label.length);
  const leading = named.filter((n) => message.startsWith(`'${n.label}'`));
  if (leading.length) {
    const len = leading[0].label.length;
    return leading.filter((n) => n.label.length === len).map((n) => n.id);
  }
  return named.filter((n) => message.includes(`'${n.label}'`)).map((n) => n.id);
}

/** node id -> { errors: [...], warnings: [...] } */
export function problemsByNode(validation, nodes) {
  const map = {};
  const add = (kind) => (msg) => nodesMentioned(msg, nodes).forEach((id) => {
    map[id] = map[id] || { errors: [], warnings: [] };
    map[id][kind].push(msg);
  });
  validation.errors.forEach(add('errors'));
  validation.warnings.forEach(add('warnings'));
  return map;
}

// ---------- runs ----------

export const ACTIVE = ['queued', 'running'];
export const isActive = (run) => !!run && ACTIVE.includes(run.status);
export const SOURCE_LABELS = { form: 'Run form', form_link: 'Form link', chat: 'Chat', schedule: 'Schedule', webhook: 'Webhook', test: 'Test', api: 'API' };

export function parseDate(value) {
  if (!value) return null;
  const s = String(value);
  return new Date(/Z$|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}

export function formatDuration(ms) {
  if (ms == null || Number.isNaN(ms)) return '';
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${Math.round(s - m * 60)} s`;
}

/** Duration between two timestamps; an unfinished one counts up to `now`. */
export function durationOf(start, end, now = Date.now()) {
  const a = parseDate(start);
  if (!a) return null;
  const b = parseDate(end);
  return (b ? b.getTime() : now) - a.getTime();
}

/** Re-render every `ms` while `on` (for durations that count up). */
export function useNow(on, ms = 500) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return undefined;
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [on, ms]);
  return now;
}

/** Follow a run until it finishes: GET /runs/{id} every `ms` while it is queued or running. */
export function useRunPolling(run, setRun, ms = 700) {
  const id = run?.id;
  const active = isActive(run);
  useEffect(() => {
    if (!id || !active) return undefined;
    let stop = false;
    const t = setTimeout(async () => {
      try {
        const next = (await api.get(`/runs/${id}`)).data;
        if (!stop) setRun((cur) => (cur && cur.id === id ? next : cur));
      } catch {
        // Network blip: try again on the next tick (a new object re-arms this effect).
        if (!stop) setRun((cur) => (cur && cur.id === id ? { ...cur } : cur));
      }
    }, ms);
    return () => {
      stop = true;
      clearTimeout(t);
    };
    // Every response is a new object, so each poll schedules the next one.
  }, [id, active, run, setRun, ms]);
}

/**
 * Per-step state of a run, keyed by node id: { status, continued, attempts, error, ... }.
 * Uses the live `nodes` records; older runs only have the `steps` trace.
 */
export function nodeStates(run) {
  if (!run) return {};
  if (run.nodes?.length) return Object.fromEntries(run.nodes.map((n) => [n.node_id, n]));
  const out = {};
  (run.steps || []).forEach((s) => {
    if (!s.node_id) return;
    const continued = s.status === 'error_continued';
    out[s.node_id] = { ...s, status: continued ? 'failed' : s.status, continued };
  });
  return out;
}

/** The status shown on the canvas for one step ("continued" = failed but the workflow kept going). */
export function displayStatus(state) {
  if (!state) return null;
  if (state.continued) return 'continued';
  return state.status;
}

/** Canvas look of a step per run status: the card's border/ring and the label colour. */
export const NODE_RUN_STYLE = {
  pending: { card: 'border-line opacity-80', text: 'text-muted-strong', label: 'waiting' },
  running: { card: 'border-sky-500 ring-4 ring-sky-200', text: 'text-sky-700', label: 'running' },
  success: { card: 'border-green-500 ring-2 ring-green-100', text: 'text-green-700', label: 'done' },
  failed: { card: 'border-red-500 ring-4 ring-red-200', text: 'text-red-700', label: 'failed' },
  continued: { card: 'border-amber-500 ring-2 ring-amber-100', text: 'text-amber-800', label: 'failed, kept going' },
  skipped: { card: 'border-dashed border-line opacity-50', text: 'text-muted-strong', label: 'skipped' },
  cancelled: { card: 'border-slate-400 opacity-70', text: 'text-slate-600', label: 'cancelled' },
};
