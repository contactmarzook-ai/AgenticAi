import { useEffect, useState } from 'react';
import api, { errorMessage } from '../lib/api';
import { CATEGORY_STYLE, iconFor } from '../lib/icons';
import { Alert, Button, Checkbox, Field, Input, PageHeader, Select, Textarea, cx } from '../lib/ui';

export default function Settings() {
  const [s, setS] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [hosts, setHosts] = useState('');
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/settings').then((r) => {
      setS(r.data);
      setHosts((r.data.http_allowed_hosts || []).join('\n'));
    });
    api.get('/nodes').then((r) => setNodes(r.data.nodes));
  }, []);

  if (!s) return null;
  const disabled = new Set(s.disabled_nodes);
  const toggle = (key) => {
    const next = new Set(disabled);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setS({ ...s, disabled_nodes: [...next] });
  };

  const save = async () => {
    if (!s.run_retention_days && !confirm('Run history will be kept forever (0 days). Continue?')) return;
    setSaving(true);
    try {
      const body = { ...s, http_allowed_hosts: hosts.split(/[\n,]/).map((h) => h.trim()).filter(Boolean) };
      const res = (await api.put('/settings', body)).data;
      setS(res);
      setHosts(res.http_allowed_hosts.join('\n'));
      const affected = res.affected_automations || [];
      setNotice(affected.length
        ? { kind: 'info', text: `Saved. These workflows use a step you just turned off and will fail until changed: ${affected.map((a) => `${a.name} (${a.status === 'active' ? 'live' : a.status})`).join(', ')}.` }
        : { kind: 'success', text: 'Settings saved. They apply to new runs immediately.' });
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Platform settings" subtitle="What builders can use, and what workflows may reach." actions={<Button loading={saving} onClick={save}>Save settings</Button>} />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}

        <section className="space-y-3 rounded-xl border bg-white p-5">
          <h2 className="font-semibold text-gray-900">Available steps</h2>
          <p className="text-sm text-gray-500">Untick a step to remove it from the builder and block it in every workflow, including existing ones.</p>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {nodes.map((n) => {
              const Icon = iconFor(n.icon);
              const st = CATEGORY_STYLE[n.category];
              return (
                <label key={n.key} className={cx('flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm', disabled.has(n.key) && 'bg-gray-50 opacity-60')}>
                  <input type="checkbox" className="mt-1" checked={!disabled.has(n.key)} onChange={() => toggle(n.key)} />
                  <span className={cx('mt-0.5 rounded p-1', st.bg)}><Icon className={cx('h-3.5 w-3.5', st.text)} /></span>
                  <span>
                    <span className="font-medium">{n.name}</span> <span className="text-xs text-gray-400">{n.category}</span>
                    <span className="block text-xs text-gray-500">{n.description}</span>
                  </span>
                </label>
              );
            })}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border bg-white p-5">
          <h2 className="font-semibold text-gray-900">Outbound HTTP</h2>
          <Field label="Hosts that HTTP request steps may call" hint="One host per line, e.g. api.example.com (a pasted URL is reduced to its host). Use *.example.com for subdomains, or * for any public host. Slack/Teams/email connections are not limited by this list.">
            <Textarea rows={5} value={hosts} onChange={(e) => setHosts(e.target.value)} placeholder={'api.yourcompany.com\n*.salesforce.com'} />
          </Field>
          <Checkbox label="Allow private / internal network addresses (intranet APIs). Leave off unless needed: it lets workflows reach internal systems." checked={!!s.allow_private_network} onChange={(e) => setS({ ...s, allow_private_network: e.target.checked })} />
        </section>

        <section className="grid gap-4 rounded-xl border bg-white p-5 md:grid-cols-2">
          <Field label="Who can create connections">
            <Select value={s.connections_min_role} onChange={(e) => setS({ ...s, connections_min_role: e.target.value })}>
              <option value="builder">Builders and admins</option>
              <option value="admin">Admins only</option>
            </Select>
          </Field>
          <Field label="Keep run history for (days)" hint="0 keeps it forever. The audit log is never deleted.">
            <Input type="number" min="0" max="3650" value={s.run_retention_days ?? 90} onChange={(e) => setS({ ...s, run_retention_days: Number(e.target.value) })} />
          </Field>
          <Field label="Longest Wait step (seconds)">
            <Input type="number" min="0" max="3600" value={s.max_wait_seconds} onChange={(e) => setS({ ...s, max_wait_seconds: Number(e.target.value) })} />
          </Field>
          <div className="pt-6">
            <Checkbox label="AI builder (create workflows from a description)" checked={!!s.ai_builder_enabled} onChange={(e) => setS({ ...s, ai_builder_enabled: e.target.checked })} />
          </div>
        </section>
      </div>
    </div>
  );
}
