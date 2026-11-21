import { useState } from 'react';
import {
  Ban, CircleCheck, CircleDashed, CircleX, FlaskConical, Loader2, LocateFixed, Play, RotateCcw, Square, TriangleAlert, X,
} from 'lucide-react';
import api, { errorMessage } from '../../lib/api';
import { Alert, Button, JsonBlock, Modal, StatusBadge, cx, formatDate } from '../../lib/ui';
import { ResultView } from '../RunSteps';
import RunForm, { missingRequired } from './RunForm';
import { NODE_RUN_STYLE, SOURCE_LABELS, displayStatus, durationOf, formatDuration, isActive, useNow } from './execution';

const ICONS = { pending: CircleDashed, running: Loader2, success: CircleCheck, failed: CircleX, continued: TriangleAlert, skipped: CircleDashed, cancelled: Ban };

/** Small status icon for a step (canvas cards and step lists). */
export function NodeRunIcon({ status, className }) {
  const Icon = ICONS[status];
  if (!Icon) return null;
  return (
    <Icon
      aria-label={NODE_RUN_STYLE[status]?.label || status}
      className={cx('h-4 w-4 flex-shrink-0', NODE_RUN_STYLE[status]?.text, status === 'running' && 'animate-spin', className)}
    />
  );
}

function RunDuration({ run }) {
  const now = useNow(isActive(run));
  if (run.status === 'queued') return <span className="text-muted-strong">waiting to start…</span>;
  const ms = durationOf(run.started_at || run.created_at, run.finished_at, now);
  return <span className="tabular-nums text-muted-strong">{formatDuration(ms)}</span>;
}

/** Floating bar on the canvas while a run is shown: status, duration, Cancel, back to editing. */
export function RunBar({ run, onCancel, cancelling, onClear, onShowDetails, otherVersion }) {
  const active = isActive(run);
  return (
    <div className="glass-strong pointer-events-auto flex max-w-full items-center gap-2 rounded-lg border px-3 py-1.5 text-xs shadow-lift">
      {active ? <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" /> : <NodeRunIcon status={run.status === 'succeeded' ? 'success' : run.status === 'failed' ? 'failed' : 'cancelled'} className="h-3.5 w-3.5" />}
      <button type="button" onClick={onShowDetails} className="font-medium text-navy hover:underline">
        {run.source === 'test' ? 'Test' : 'Run'} #{run.id}
      </button>
      <span data-testid="run-status" data-status={run.status}><StatusBadge status={run.status} /></span>
      <RunDuration run={run} />
      {otherVersion && <span className="text-amber-800">ran another version</span>}
      {run.cancel_requested && active && <span className="text-muted-strong">stopping…</span>}
      {active && (
        <Button data-testid="cancel-run" variant="danger" className="!px-2 !py-0.5 text-xs" icon={Square} loading={cancelling} disabled={run.cancel_requested} onClick={onCancel}>
          Cancel
        </Button>
      )}
      {!active && (
        <button type="button" onClick={onClear} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-muted-strong hover:bg-brand-50 hover:text-brand-700" title="Hide the run and go back to editing">
          <X className="h-3.5 w-3.5" /> Back to editing
        </button>
      )}
    </div>
  );
}

/** Details of one step in the shown run: status, attempts, duration, logs, input, output, error. */
export function NodeRunDetails({ state, run }) {
  const status = displayStatus(state);
  const ms = durationOf(state.started_at, state.finished_at);
  return (
    <div data-testid="node-run" data-run-status={status} className="space-y-2 rounded-md border border-navy-100 bg-navy-50/60 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold uppercase text-muted-strong">{run.source === 'test' ? 'Last test' : `Run #${run.id}`}</span>
        <NodeRunIcon status={status} />
        <span className={cx('font-medium', NODE_RUN_STYLE[status]?.text)}>{NODE_RUN_STYLE[status]?.label || status}</span>
        {state.attempts > 1 && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800">{state.attempts} attempts</span>}
        {ms != null && state.started_at && <span className="text-muted-strong">{formatDuration(ms)}</span>}
      </div>
      {state.error && <Alert>{state.error}</Alert>}
      {!['pending', 'skipped'].includes(status) && (
        <div>
          <div className="mb-0.5 text-xs font-medium text-muted-strong">Logs</div>
          {state.logs?.length ? (
            <ol className="max-h-48 overflow-auto rounded border bg-surface p-2 font-mono text-[11px] leading-relaxed text-ink">
              {state.logs.map((line, i) => <li key={i} className="whitespace-pre-wrap break-words">{typeof line === 'string' ? line : JSON.stringify(line)}</li>)}
            </ol>
          ) : (
            <p className="text-xs text-muted-strong">Nothing logged (retries and interruptions are logged here).</p>
          )}
        </div>
      )}
      {state.input !== undefined && state.input !== null && (
        <details open={!state.output}>
          <summary className="cursor-pointer text-xs font-medium text-muted-strong">Input</summary>
          <div className="mt-1"><JsonBlock value={state.input} /></div>
        </details>
      )}
      {state.output !== undefined && state.output !== null && (
        <div>
          <div className="mb-0.5 text-xs font-medium text-muted-strong">Output</div>
          <JsonBlock value={state.output} />
        </div>
      )}
      {status === 'pending' && <p className="text-xs text-muted-strong">This step has not run yet.</p>}
      {status === 'skipped' && <p className="text-xs text-muted-strong">This step did not run (another path was taken, or an earlier step failed).</p>}
    </div>
  );
}

/** The "Run" tab: what happened in the shown run, with failure details, result and every step. */
export default function RunPanel({ run, states, nodes, versionOf, otherVersion, onSelectNode, onRerun, rerunning, onOpenVersion }) {
  const failedId = Object.keys(states).find((id) => states[id].status === 'failed' && !states[id].continued);
  const failed = failedId ? states[failedId] : null;
  const steps = (run.nodes?.length ? [...run.nodes].sort((a, b) => a.seq - b.seq) : (run.steps || []).filter((s) => s.node_id).map((s) => ({ ...s, ...states[s.node_id] })));
  const onCanvas = (id) => !otherVersion && nodes.some((n) => n.id === id);
  const version = versionOf(run.target_id);
  return (
    <div data-testid="run-panel" data-status={run.status} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold text-navy">{run.source === 'test' ? 'Test' : 'Run'} #{run.id}</h3>
        <StatusBadge status={run.status} />
        <span className="text-xs"><RunDuration run={run} /></span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-strong">
        <span>{SOURCE_LABELS[run.source] || run.source}</span>
        {version != null && <span>version {version}</span>}
        <span>started {formatDate(run.created_at)}</span>
        {run.resume_count > 0 && <span>resumed {run.resume_count}×</span>}
      </div>
      {otherVersion && (
        <Alert kind="info">
          This run used {version != null ? `version ${version}` : 'another version'}, not the one open here, so it is not drawn on the canvas.
          {onOpenVersion && <> <button type="button" className="font-medium underline" onClick={onOpenVersion}>Open that version</button></>}
        </Alert>
      )}
      {run.status === 'failed' && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <div className="mb-1 flex items-center gap-1.5 font-semibold"><CircleX className="h-4 w-4" /> The run failed{failed ? ` at “${failed.label || failedId}”` : ''}</div>
          <p className="whitespace-pre-wrap break-words">{run.error || failed?.error || 'No error message was recorded.'}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {failed && onCanvas(failedId) && <Button variant="secondary" icon={LocateFixed} onClick={() => onSelectNode(failedId)}>Show the failed step</Button>}
            {onRerun && <Button variant="secondary" icon={RotateCcw} loading={rerunning} onClick={onRerun}>Re-run</Button>}
          </div>
        </div>
      )}
      {run.status === 'cancelled' && (
        <Alert kind="info">The run was cancelled{run.error && run.error !== 'Run was cancelled' ? `: ${run.error}` : '.'} Steps that had not started were not run.</Alert>
      )}
      {run.status === 'succeeded' && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-muted-strong">Result</div>
          <ResultView value={run.output?.result} />
        </div>
      )}
      {onRerun && ['succeeded', 'cancelled'].includes(run.status) && (
        <Button variant="secondary" icon={RotateCcw} loading={rerunning} onClick={onRerun}>Run again with the same input</Button>
      )}
      <div>
        <div className="mb-1 text-xs font-semibold uppercase text-muted-strong">Steps</div>
        {!steps.length && <p className="text-sm text-muted-strong">{isActive(run) ? 'Starting…' : 'No steps recorded.'}</p>}
        {steps.length > 0 && <ol className="divide-y rounded-md border">
          {steps.map((s) => {
            const st = displayStatus(states[s.node_id] || s);
            const ms = durationOf(s.started_at, s.finished_at);
            return (
              <li key={s.node_id}>
                <button
                  type="button"
                  disabled={!onCanvas(s.node_id)}
                  onClick={() => onSelectNode(s.node_id)}
                  className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm enabled:hover:bg-brand-50"
                >
                  <NodeRunIcon status={st} />
                  <span className="min-w-0 flex-1 truncate text-ink">{s.label || s.node_id}</span>
                  {s.attempts > 1 && <span className="text-[11px] text-amber-800">×{s.attempts}</span>}
                  {s.started_at && ms != null && <span className="text-[11px] tabular-nums text-muted-strong">{formatDuration(ms)}</span>}
                  <span className={cx('w-16 text-right text-[11px]', NODE_RUN_STYLE[st]?.text)}>{NODE_RUN_STYLE[st]?.label || st}</span>
                </button>
              </li>
            );
          })}
        </ol>}
        {steps.length > 0 && !otherVersion && <p className="mt-1 text-xs text-muted-strong">Click a step to see its input, output and logs.</p>}
      </div>
    </div>
  );
}

/** Ask for the Start form's input, then start a test (any version) or a run (published version). */
export function StartRunDialog({ workflow, fields, mode = 'test', onClose, onStarted }) {
  const [input, setInput] = useState({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const isTest = mode === 'test';

  const go = async () => {
    const missing = missingRequired(fields, input);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ')}`);
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = isTest
        ? (await api.post(`/workflows/${workflow.id}/test`, { input }, { params: { background: true } })).data
        : (await api.post(`/workflows/${workflow.id}/run`, { input })).data;
      onStarted(res);
    } catch (err) {
      setError(errorMessage(err));
      setLoading(false);
    }
  };

  return (
    <Modal wide title={isTest ? `Test “${workflow.name}”` : `Run version ${workflow.version} of “${workflow.name}”`} onClose={onClose}>
      <div className="space-y-3">
        {!isTest && <p className="text-sm text-muted-strong">This runs the published version {workflow.version} exactly as it was published.</p>}
        <RunForm fields={fields} value={input} onChange={setInput} />
        <Button icon={isTest ? FlaskConical : Play} loading={loading} onClick={go}>{isTest ? 'Run test' : 'Run this version'}</Button>
        <p className="text-xs text-muted-strong">You can follow each step on the canvas while it runs, and cancel it.</p>
        <Alert>{error}</Alert>
      </div>
    </Modal>
  );
}
