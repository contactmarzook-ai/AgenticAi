import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, Download, History, LayoutTemplate, Play, Plus, Power, Search, Sparkles, Trash2, Upload, Wand2 } from 'lucide-react';
import { isAdmin } from '../lib/roles';
import api, { errorMessage } from '../lib/api';
import { can } from '../lib/auth';
import { Alert, Badge, Button, Empty, Modal, StatusBadge, formatDate } from '../lib/ui';
import RunForm, { missingRequired } from './automation/RunForm';
import RunSteps, { ResultView } from './RunSteps';

const FlowBuilder = lazy(() => import('./automation/FlowBuilder'));

const EXAMPLES = [
  'When a support ticket comes in, decide if it is urgent and draft a reply',
  'Every morning, write a short team briefing and post it to Teams',
  'Read an invoice, pull out the total and due date, and flag anything over 10,000',
  'Check our website every 15 minutes and email IT if it is down',
];

export default function Automations({ user }) {
  const canBuild = can(user, 'workflow:write');
  const [workflows, setWorkflows] = useState([]);
  const [catalog, setCatalog] = useState({ nodes: [], credential_types: [] });
  const [agents, setAgents] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [settings, setSettings] = useState({});
  const [open, setOpen] = useState(undefined); // undefined = list; {workflow?, draft?}
  const [running, setRunning] = useState(null);
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [info, setInfo] = useState('');

  const load = useCallback(() => api.get('/workflows').then((r) => setWorkflows(r.data)).catch((e) => setError(errorMessage(e))), []);

  // Deep link: #/workflows/<id> reopens the builder after a refresh.
  useEffect(() => {
    const m = window.location.hash.match(/^#\/(?:workflows|automations)\/(\d+)/);
    if (m) api.get(`/workflows/${m[1]}`).then((r) => setOpen({ workflow: r.data })).catch(() => window.history.replaceState(null, '', '#/workflows'));
  }, []);

  useEffect(() => {
    const home = () => {
      window.history.replaceState(null, '', '#/workflows');
      setOpen(undefined);
      load();
    };
    window.addEventListener('stardust:home', home);
    return () => window.removeEventListener('stardust:home', home);
  }, [load]);

  useEffect(() => {
    load();
    api.get('/nodes').then((r) => setCatalog(r.data)).catch(() => {});
    api.get('/agents').then((r) => setAgents(r.data)).catch(() => {});
    api.get('/settings').then((r) => setSettings(r.data)).catch(() => {});
    if (canBuild) api.get('/templates').then((r) => setTemplates(r.data)).catch(() => {});
  }, [load, canBuild]);

  // One card per workflow (group): prefer the live version, otherwise the newest draft.
  const groups = useMemo(() => {
    const byGroup = new Map();
    workflows.forEach((w) => byGroup.set(w.group_id, [...(byGroup.get(w.group_id) || []), w]));
    return [...byGroup.values()]
      .map((versions) => {
        versions.sort((a, b) => b.version - a.version);
        return { latest: versions[0], live: versions.find((v) => v.status === 'active'), lastOff: versions.find((v) => v.status === 'archived') };
      })
      .sort((a, b) => new Date(b.latest.updated_at) - new Date(a.latest.updated_at))
      .filter(({ latest, live }) => `${(live || latest).name} ${(live || latest).description || ''}`.toLowerCase().includes(query.toLowerCase()));
  }, [workflows, query]);

  const generate = async () => {
    setGenerating(true);
    setError('');
    try {
      const res = (await api.post('/workflows/generate', { prompt })).data;
      setOpen({ draft: res });
      setPrompt('');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  const [creating, setCreating] = useState(false);
  const applyTemplate = async (t) => {
    if (creating) return;
    setCreating(true);
    try {
      const wf = (await api.post(`/templates/${t.key}/use`)).data;
      setShowTemplates(false);
      load();
      setOpen({ workflow: wf });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const act = async (fn, okMsg) => {
    setError('');
    try {
      await fn();
      if (okMsg) setInfo(okMsg);
      load();
    } catch (err) {
      setError(err?.response || err?.request ? errorMessage(err) : err.message);
    }
  };

  const exportJson = (wf) => {
    const blob = new Blob([JSON.stringify({ agentos: 1, name: wf.name, description: wf.description, definition: wf.definition }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${wf.name.replace(/[^\w-]+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = (file) => {
    const reader = new FileReader();
    reader.onload = () => act(async () => {
      let data;
      try {
        data = JSON.parse(reader.result);
      } catch {
        throw new Error('That file is not a Star Dust workflow (not valid JSON).');
      }
      if (!data?.definition?.nodes) throw new Error('That file is not a Star Dust workflow.');
      const wf = (await api.post('/workflows', { name: data.name || file.name, description: data.description || null, definition: data.definition })).data;
      setOpen({ workflow: wf });
    });
    reader.readAsText(file);
  };

  if (open !== undefined) {
    return (
      <Suspense fallback={<div className="p-6 text-sm text-muted-strong">Loading builder…</div>}>
        <FlowBuilder
          key={open.workflow?.id ?? 'new'}
          workflow={open.workflow}
          draft={open.draft}
          catalog={catalog.nodes}
          credentialTypes={catalog.credential_types}
          agents={agents}
          user={user}
          onSaved={load}
          onBack={() => { window.history.replaceState(null, '', '#/workflows'); setOpen(undefined); load(); }}
          onOpenVersion={(v, extra) => setOpen({ workflow: v, runId: extra?.runId })}
          initialRunId={open.runId}
        />
      </Suspense>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6 sm:py-8">
        {canBuild && (
          <section className="glass rounded-xl border p-4 shadow-card sm:p-6">
            <h1 className="flex items-center gap-2 text-xl font-semibold text-navy">
              <Sparkles className="h-5 w-5 text-accent-600" /> What would you like to automate?
            </h1>
            <p className="mt-1 text-sm text-muted-strong">Describe it in plain words. AI drafts the steps; you review, test and publish.</p>
            {settings.ai_builder_enabled !== false ? (
              <>
                <textarea
                  value={prompt}
                  maxLength={4000}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  placeholder="e.g. When a customer emails a complaint, summarize it, decide how urgent it is, and post urgent ones to Slack"
                  className="mt-4 w-full resize-none rounded-lg border border-navy-100 px-3 py-2.5 text-sm transition-[border-color,box-shadow] duration-150 placeholder:text-muted bg-white/90 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-brand-500/20"
                />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {EXAMPLES.map((ex) => (
                    <button key={ex} onClick={() => setPrompt(ex)} className="rounded-full border border-navy-100 bg-white/70 px-2.5 py-1 text-xs text-muted-strong transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700">{ex}</button>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-3 text-sm text-muted-strong">The AI builder is turned off by your administrator.</p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              {settings.ai_builder_enabled !== false && (
                <Button icon={Wand2} loading={generating} disabled={prompt.trim().length < 5} onClick={generate} className="!bg-accent !text-navy-900 hover:!bg-accent-600 disabled:!bg-accent-100 disabled:!text-muted-strong">
                  {generating ? 'Drafting… (local models can take a minute)' : 'Create with AI'}
                </Button>
              )}
              <Button variant="secondary" icon={LayoutTemplate} onClick={() => setShowTemplates(true)}>Start from a template</Button>
              <Button variant="ghost" icon={Plus} onClick={() => setOpen({})}>Start blank</Button>
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-strong hover:bg-brand-50">
                <Upload className="h-4 w-4" /> Import
                <input type="file" accept="application/json,.json" className="hidden" onChange={(e) => { if (e.target.files?.[0]) importJson(e.target.files[0]); e.target.value = ''; }} />
              </label>
            </div>
            <div className="mt-3"><Alert>{error}</Alert></div>
          </section>
        )}

        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-navy">Your workflows</h2>
            {info && <span className="text-sm text-green-700">{info}</span>}
            {groups.length > 4 || query ? (
              <div className="relative">
                <Search className="absolute left-2 top-2 h-4 w-4 text-muted" />
                <input className="rounded-md border border-navy-100 py-1.5 pl-7 pr-2 text-sm placeholder:text-muted bg-white/90 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-brand-500/20" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
              </div>
            ) : null}
          </div>
          {!groups.length ? (
            <Empty>{canBuild ? 'Nothing yet. Describe one above or pick a template.' : 'No workflows are shared with you yet.'}</Empty>
          ) : (
            <div className="glass divide-y divide-line/80 rounded-lg border shadow-card">
              {groups.map(({ latest, live, lastOff }) => {
                const wf = live || latest;
                const off = !live && !!lastOff;
                const isOwner = isAdmin(user) || latest.owner_id === user.id;
                return (
                  <div key={latest.group_id} className="flex flex-wrap items-center gap-2 px-5 py-4 transition-colors duration-150 first:rounded-t-lg last:rounded-b-lg hover:bg-white/60">
                    <div className="min-w-[14rem] flex-1">
                      <div className="flex items-center gap-2">
                        <button className="truncate font-medium text-ink hover:underline" onClick={() => setOpen({ workflow: latest })}>{wf.name}</button>
                        {live ? <Badge color="green">live</Badge> : off ? <Badge color="red">off</Badge> : <Badge color="yellow">draft</Badge>}
                        {(live || off) && latest.status === 'draft' && <Badge>newer draft</Badge>}
                      </div>
                      <p className="truncate text-sm text-muted-strong">{wf.description || 'No description'}</p>
                      <p className="text-xs text-muted-strong">Updated {formatDate(latest.updated_at)}</p>
                    </div>
                    {live && can(user, 'workflow:run') && <Button variant="secondary" icon={Play} onClick={() => setRunning(live)}>Run</Button>}
                    {off && lastOff.can_edit && can(user, 'workflow:activate') && (
                      <Button variant="secondary" icon={Power} onClick={() => act(() => api.post(`/workflows/${lastOff.id}/activate`), `“${wf.name}” (version ${lastOff.version}) is live again.`)}>Turn on</Button>
                    )}
                    <Button variant="ghost" onClick={() => setOpen({ workflow: latest })}>{latest.can_edit ? 'Edit' : 'View'}</Button>
                    <button title="History" aria-label="History" className="rounded p-1.5 text-muted-strong hover:bg-brand-50" onClick={() => { window.location.hash = `#/runs?group=${latest.group_id}&name=${encodeURIComponent(wf.name)}`; }}><History className="h-4 w-4" /></button>
                    {canBuild && <button title="Duplicate" aria-label="Duplicate" className="rounded p-1.5 text-muted-strong hover:bg-brand-50" onClick={() => act(() => api.post(`/workflows/${wf.id}/duplicate`), `Copied “${wf.name}”.`)}><Copy className="h-4 w-4" /></button>}
                    {canBuild && <button title="Export as a file" aria-label="Export" className="rounded p-1.5 text-muted-strong hover:bg-brand-50" onClick={() => exportJson(latest)}><Download className="h-4 w-4" /></button>}
                    {canBuild && isOwner && (
                      <button title="Delete" aria-label="Delete" className="rounded p-1.5 text-muted-strong hover:bg-red-50 hover:text-red-600"
                        onClick={() => confirm(`Delete “${wf.name}” with all its versions, schedules, form links and webhooks? Run history is kept.`) && act(() => api.delete(`/workflows/groups/${latest.group_id}`), `Deleted “${wf.name}”.`)}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {showTemplates && (
        <Modal wide title="Templates" onClose={() => setShowTemplates(false)}>
          <div className="grid gap-3 md:grid-cols-2">
            {templates.map((t) => (
              <button key={t.key} disabled={creating} onClick={() => applyTemplate(t)} className="glass-hover rounded-lg border border-navy-100 bg-white/75 p-4 text-left hover:border-brand-300 hover:bg-white">
                <div className="text-xs font-medium uppercase text-muted-strong">{t.category}</div>
                <div className="font-medium text-ink">{t.name}</div>
                <p className="mt-1 text-sm text-muted-strong">{t.description}</p>
                <p className="mt-2 text-xs text-muted-strong">
                  {t.steps} steps{t.needs.length ? ` · needs a ${t.needs.map((n) => catalog.credential_types.find((c) => c.key === n)?.name || n).join(', ')} connection` : ' · works right away'}
                </p>
              </button>
            ))}
          </div>
        </Modal>
      )}
      {running && <RunAutomation workflow={running} onClose={() => setRunning(null)} />}
    </div>
  );
}

function RunAutomation({ workflow, onClose }) {
  const fields = workflow.definition?.nodes?.find((n) => n.type === 'input')?.data?.fields || [];
  const [input, setInput] = useState({});
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!run || ['succeeded', 'failed'].includes(run.status)) return;
    const t = setTimeout(() => api.get(`/runs/${run.id}`).then((r) => setRun(r.data)), 1000);
    return () => clearTimeout(t);
  }, [run]);

  const start = async () => {
    const missing = missingRequired(fields, input);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ')}`);
      return;
    }
    setError('');
    try {
      setRun((await api.post(`/workflows/${workflow.id}/run`, { input, from_form: true })).data);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const finished = run && ['succeeded', 'failed'].includes(run.status);
  const result = run?.output?.result;
  return (
    <Modal wide title={`Run “${workflow.name}”`} onClose={onClose}>
      <div className="space-y-4">
        {!run && (
          <>
            <RunForm fields={fields} value={input} onChange={setInput} />
            <Button icon={Play} onClick={start}>Run now</Button>
          </>
        )}
        <Alert>{error}</Alert>
        {run && !finished && <p className="text-sm text-muted-strong">Running… <StatusBadge status={run.status} /></p>}
        {finished && (
          <div className="space-y-3">
            {run.status === 'failed' ? <Alert>{run.error}</Alert> : (
              <ResultView value={result} />
            )}
            <details>
              <summary className="cursor-pointer text-sm text-muted-strong">Step by step</summary>
              <div className="mt-2"><RunSteps steps={run.steps} /></div>
            </details>
            <Button variant="secondary" onClick={() => { setRun(null); }}>Run again</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
