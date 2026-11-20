import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { GitBranch, Play, Plus } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Badge, Button, Empty, Field, Modal, PageHeader, StatusBadge, Textarea, formatDate } from '../lib/ui';
import RunSteps from './RunSteps';

const WorkflowBuilder = lazy(() => import('./WorkflowBuilder'));

export default function Workflows({ user }) {
  const [workflows, setWorkflows] = useState([]);
  const [agents, setAgents] = useState([]);
  const [tools, setTools] = useState([]);
  const [editing, setEditing] = useState(undefined); // undefined = list, null = new, object = existing version
  const [running, setRunning] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => api.get('/workflows').then((r) => setWorkflows(r.data)).catch((e) => setError(errorMessage(e))), []);

  useEffect(() => {
    load();
    api.get('/agents').then((r) => setAgents(r.data)).catch(() => {});
    if (can(user, 'tool:read')) api.get('/tools').then((r) => setTools(r.data)).catch(() => {});
  }, [load, user]);

  // One card per workflow group: active version (if any) plus the newest draft.
  const groups = useMemo(() => {
    const byGroup = new Map();
    for (const w of workflows) {
      if (!byGroup.has(w.group_id)) byGroup.set(w.group_id, []);
      byGroup.get(w.group_id).push(w);
    }
    return [...byGroup.values()].map((versions) => {
      versions.sort((a, b) => b.version - a.version);
      return { latest: versions[0], active: versions.find((v) => v.status === 'active'), versions };
    });
  }, [workflows]);

  if (editing !== undefined) {
    return (
      <Suspense fallback={<div className="p-6 text-sm text-gray-500">Loading builder…</div>}>
      <WorkflowBuilder
        key={editing?.id ?? 'new'}
        workflow={editing}
        agents={agents}
        tools={tools}
        user={user}
        onSaved={load}
        onBack={() => {
          setEditing(undefined);
          load();
        }}
      />
      </Suspense>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Workflows"
        subtitle="Chain agents, tools and conditions. Drafts are tested first, then activated."
        actions={
          can(user, 'workflow:write') && (
            <Button icon={Plus} onClick={() => setEditing(null)}>
              New workflow
            </Button>
          )
        }
      />
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        <Alert>{error}</Alert>
        {!groups.length && <Empty>No workflows yet.</Empty>}
        {groups.map(({ latest, active, versions }) => (
          <div key={latest.group_id} className="flex flex-wrap items-center gap-4 rounded-lg border bg-white p-4 shadow-sm">
            <div className="rounded-md bg-purple-50 p-2">
              <GitBranch className="h-5 w-5 text-purple-600" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900">{(active || latest).name}</h3>
                <Badge>{latest.visibility}</Badge>
              </div>
              <p className="truncate text-sm text-gray-500">{(active || latest).description || 'No description.'}</p>
              <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-gray-500">
                {versions.map((v) => (
                  <button key={v.id} onClick={() => setEditing(v)} className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 hover:bg-gray-50">
                    v{v.version} <StatusBadge status={v.status} />
                  </button>
                ))}
                <span>updated {formatDate(latest.updated_at)}</span>
              </div>
            </div>
            <div className="flex gap-2">
              {active && can(user, 'workflow:run') && (
                <Button variant="secondary" icon={Play} onClick={() => setRunning(active)}>
                  Run
                </Button>
              )}
              <Button variant="secondary" onClick={() => setEditing(latest)}>
                {latest.can_edit ? 'Open builder' : 'View'}
              </Button>
            </div>
          </div>
        ))}
      </div>
      {running && <RunWorkflow workflow={running} onClose={() => setRunning(null)} />}
    </div>
  );
}

function RunWorkflow({ workflow, onClose }) {
  const [input, setInput] = useState('{\n  "message": ""\n}');
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!run || ['succeeded', 'failed'].includes(run.status)) return;
    const t = setTimeout(() => api.get(`/runs/${run.id}`).then((r) => setRun(r.data)), 1000);
    return () => clearTimeout(t);
  }, [run]);

  const start = async () => {
    let parsed;
    try {
      parsed = JSON.parse(input);
    } catch {
      setError('Input must be valid JSON');
      return;
    }
    setError('');
    try {
      setRun((await api.post(`/workflows/${workflow.id}/run`, { input: parsed })).data);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const finished = run && ['succeeded', 'failed'].includes(run.status);
  return (
    <Modal wide title={`Run “${workflow.name}” (v${workflow.version})`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="Input (JSON object)">
          <Textarea rows={4} value={input} onChange={(e) => setInput(e.target.value)} />
        </Field>
        <Button icon={Play} onClick={start} loading={run && !finished}>
          Start run
        </Button>
        <Alert>{error}</Alert>
        {run && (
          <div className="space-y-2">
            <div className="text-sm">
              Run #{run.id}: <StatusBadge status={run.status} />
            </div>
            {run.status === 'failed' && <Alert>{run.error}</Alert>}
            {run.status === 'succeeded' && (
              <pre className="max-h-60 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{JSON.stringify(run.output?.result, null, 2)}</pre>
            )}
            {finished && <RunSteps steps={run.steps} />}
          </div>
        )}
      </div>
    </Modal>
  );
}
