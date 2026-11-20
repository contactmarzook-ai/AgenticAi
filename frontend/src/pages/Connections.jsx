import { useCallback, useEffect, useState } from 'react';
import { Plug, Plus } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Empty, PageHeader, formatDate } from '../lib/ui';
import ConnectionEditor from './automation/ConnectionEditor';

export default function Connections() {
  const [items, setItems] = useState([]);
  const [types, setTypes] = useState([]);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => api.get('/credentials').then((r) => setItems(r.data)), []);
  useEffect(() => {
    load();
    api.get('/nodes').then((r) => setTypes(r.data.credential_types));
  }, [load]);

  const [notice, setNotice] = useState(null);
  const test = async (c) => {
    setNotice({ kind: 'info', text: `Testing “${c.name}”…` });
    try {
      const r = (await api.post(`/credentials/${c.id}/test`)).data;
      setNotice({ kind: r.ok ? 'success' : 'error', text: `${c.name}: ${r.message}` });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    }
  };

  const remove = async (c) => {
    let usedBy = [];
    try {
      usedBy = (await api.get(`/credentials/${c.id}/usage`)).data;
    } catch {
      /* ignore */
    }
    const warning = usedBy.length
      ? `“${c.name}” is used by: ${usedBy.map((u) => u.visible ? u.name : 'a workflow you cannot see').join(', ')}. They will fail until another connection is chosen. Delete anyway?`
      : `Delete connection “${c.name}”?`;
    if (!confirm(warning)) return;
    try {
      await api.delete(`/credentials/${c.id}`);
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Connections"
        subtitle="Saved accounts your workflows use: email, Slack, Teams, API keys. Secrets are encrypted."
        actions={<Button icon={Plus} onClick={() => setEditing({})}>New connection</Button>}
      />
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        <Alert>{error}</Alert>
        {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
        {!items.length ? (
          <Empty>No connections yet.</Empty>
        ) : (
          <div className="divide-y rounded-xl border bg-white">
            {items.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="rounded-md bg-sky-50 p-2"><Plug className="h-4 w-4 text-sky-700" /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{c.name}</span>
                    <Badge>{types.find((t) => t.key === c.type)?.name || c.type}</Badge>
                    <Badge color={c.visibility === 'private' ? 'gray' : 'blue'}>{c.visibility === 'private' ? 'only owner' : c.visibility}</Badge>
                  </div>
                  <p className="text-xs text-gray-400">
                    {Object.entries(c.public_data).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'secret values hidden'} · updated {formatDate(c.updated_at)}
                  </p>
                </div>
                {c.can_edit && (
                  <>
                    <Button variant="ghost" onClick={() => test(c)}>Test</Button>
                    <Button variant="ghost" onClick={() => setEditing(c)}>Edit</Button>
                    <Button variant="ghost" onClick={() => remove(c)}>Delete</Button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {editing && (
        <ConnectionEditor
          types={types}
          existing={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}
