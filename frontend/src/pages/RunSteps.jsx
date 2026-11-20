import { Badge, JsonBlock, StatusBadge } from '../lib/ui';

const isPlain = (v) => v === null || ['string', 'number', 'boolean'].includes(typeof v);

/** Friendly display of an automation's result: text as text, flat objects as a labelled list. */
export function ResultView({ value }) {
  if (value === undefined || value === null || value === '') return <p className="text-sm text-gray-500">No result.</p>;
  if (isPlain(value)) return <div className="whitespace-pre-wrap rounded-md border bg-gray-50 p-4 text-sm">{String(value)}</div>;
  if (!Array.isArray(value) && Object.values(value).every(isPlain)) {
    return (
      <dl className="divide-y rounded-md border bg-gray-50 text-sm">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="grid grid-cols-3 gap-3 px-4 py-2">
            <dt className="font-medium text-gray-600">{k.replace(/_/g, ' ')}</dt>
            <dd className="col-span-2 whitespace-pre-wrap break-words text-gray-900">{v === null ? '—' : String(v)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <JsonBlock value={value} />;
}

/** Renders the step trace of an agent or workflow run. */
export default function RunSteps({ steps }) {
  if (!steps?.length) return <p className="text-sm text-gray-500">No steps recorded.</p>;
  return (
    <ol className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="rounded-md border bg-white p-3 text-sm">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-400">#{i + 1}</span>
            {s.node_id ? (
              <>
                <Badge color="indigo">{s.type === 'action' ? s.action : s.type === 'input' ? 'start' : s.type === 'end' ? 'finish' : s.type}</Badge>
                <span className="font-medium">{s.label || s.node_id}</span>
              </>
            ) : s.type === 'tool' ? (
              <>
                <Badge color="blue">tool</Badge>
                <span className="font-mono">{s.name}</span>
              </>
            ) : (
              <Badge>LLM</Badge>
            )}
            {s.status && <StatusBadge status={s.status === 'success' ? 'succeeded' : s.status} />}
            {s.attempts > 1 && <span className="text-xs text-gray-400">{s.attempts} attempts</span>}
            {s.duration_ms != null && <span className="text-xs text-gray-400">{s.duration_ms} ms</span>}
          </div>
          {s.type === 'llm' && !s.node_id && (
            <>
              {s.content && <p className="whitespace-pre-wrap text-gray-700">{s.content}</p>}
              {s.tool_calls?.map((c, j) => (
                <div key={j} className="mt-1 font-mono text-xs text-gray-600">
                  → {c.name}({c.arguments})
                </div>
              ))}
            </>
          )}
          {s.type === 'tool' && !s.node_id && (
            <div className="space-y-1 font-mono text-xs">
              <div className="text-gray-600">args: {JSON.stringify(s.arguments)}</div>
              {s.output && <div className="break-all text-gray-800">result: {s.output}</div>}
              {s.error && <div className="text-red-600">error: {s.error}</div>}
            </div>
          )}
          {s.node_id && s.status !== 'skipped' && (
            <div className={s.input !== undefined ? 'grid gap-2 md:grid-cols-2' : ''}>
              {s.input !== undefined && (
                <div>
                  <div className="text-xs text-gray-500">input</div>
                  <JsonBlock value={s.input} />
                </div>
              )}
              <div>
                <div className="text-xs text-gray-500">{s.error ? 'error' : 'output'}</div>
                {s.error ? <p className="text-xs text-red-600">{s.error}</p> : <JsonBlock value={s.output} />}
              </div>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
