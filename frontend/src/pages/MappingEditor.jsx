import { Input, Select } from '../lib/ui';

/**
 * Edits one value mapping: where a node input comes from.
 *   static   -> fixed value
 *   input    -> a field of the workflow input
 *   node     -> a field of an earlier node's output
 *   template -> text with {{input.x}} / {{node-id.field}} placeholders
 */
export default function MappingEditor({ value, onChange, nodes, multiline }) {
  const m = value || { source: 'static', value: '' };
  const set = (patch) => onChange({ ...m, ...patch });

  return (
    <div className="space-y-1.5 rounded-md border bg-gray-50 p-2">
      <Select value={m.source === 'workflow' ? 'input' : m.source} onChange={(e) => onChange({ source: e.target.value })}>
        <option value="static">Fixed value</option>
        <option value="input">Workflow input field</option>
        <option value="node">Output of another node</option>
        <option value="template">Text template</option>
      </Select>
      {m.source === 'static' && <Input placeholder="value" value={m.value ?? ''} onChange={(e) => set({ value: e.target.value })} />}
      {(m.source === 'input' || m.source === 'workflow') && (
        <Input placeholder="field, e.g. message or customer.id (blank = whole input)" value={m.path ?? ''} onChange={(e) => set({ path: e.target.value })} />
      )}
      {m.source === 'node' && (
        <>
          <Select value={m.node_id ?? ''} onChange={(e) => set({ node_id: e.target.value })}>
            <option value="">Select node…</option>
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.data?.label || n.type} ({n.id})
              </option>
            ))}
          </Select>
          <Input placeholder="field, e.g. answer (blank = whole output)" value={m.path ?? ''} onChange={(e) => set({ path: e.target.value })} />
        </>
      )}
      {m.source === 'template' &&
        (multiline !== false ? (
          <textarea
            rows={3}
            className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 font-mono text-xs"
            placeholder="Summarise this for {{input.customer}}: {{node-123.answer}}"
            value={m.value ?? ''}
            onChange={(e) => set({ value: e.target.value })}
          />
        ) : (
          <Input value={m.value ?? ''} onChange={(e) => set({ value: e.target.value })} />
        ))}
    </div>
  );
}
