import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { can, useAuth } from '../lib/auth';
import { ROLES, ROLE_HELP, roleLabel } from '../lib/roles';
import { Alert, Badge, Button, Checkbox, Field, Input, Modal, PageHeader, Select, Table, formatDate } from '../lib/ui';

const ROLE_COLOR = { platform_admin: 'indigo', org_admin: 'indigo', developer: 'blue', auditor: 'yellow', operator: 'gray', viewer: 'gray' };

export default function Users() {
  const me = useAuth((s) => s.user);
  const platform = can(me, 'org:manage');
  const [users, setUsers] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [form, setForm] = useState(null);
  const [reset, setReset] = useState(null);
  const [orgForm, setOrgForm] = useState(null);

  const load = useCallback(() => {
    api.get('/admin/users').then((r) => setUsers(r.data));
    if (platform) api.get('/admin/orgs').then((r) => setOrgs(r.data));
  }, [platform]);
  useEffect(() => {
    load();
  }, [load]);
  const orgName = (id) => orgs.find((o) => o.id === id)?.name || '';
  const toggleOrg = async (o) => {
    await api.patch(`/admin/orgs/${o.id}`, { is_active: !o.is_active }).catch((err) => alert(errorMessage(err)));
    load();
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Users"
        subtitle={platform ? 'People and organizations. Each organization only ever sees its own agents, workflows, runs and connections.' : 'People in your organization. Department controls who sees department-shared agents and workflows.'}
        actions={
          <>
            {platform && <Button variant="secondary" icon={Plus} onClick={() => setOrgForm({ name: '', slug: '' })}>Add organization</Button>}
            <Button icon={Plus} onClick={() => setForm({ email: '', full_name: '', password: '', role: 'operator', department: '', is_active: true, org_id: me.org_id })}>Add user</Button>
          </>
        }
      />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {platform && (
          <section>
            <h2 className="mb-2 text-sm font-semibold text-navy">Organizations</h2>
            <Table
              rows={orgs}
              columns={[
                { key: 'name', label: 'Name' },
                { key: 'slug', label: 'Short name' },
                { key: 'user_count', label: 'Users' },
                { key: 'is_active', label: 'Status', render: (o) => (o.is_active ? <Badge color="green">active</Badge> : <Badge color="red">deactivated</Badge>) },
                {
                  key: 'actions',
                  label: '',
                  render: (o) => o.id !== me.org_id && (
                    <Button variant="ghost" onClick={() => toggleOrg(o)}>{o.is_active ? 'Deactivate' : 'Activate'}</Button>
                  ),
                },
              ]}
            />
          </section>
        )}
        {platform && <h2 className="-mb-4 text-sm font-semibold text-navy">Users</h2>}
        <Table
          rows={users}
          columns={[
            { key: 'email', label: 'Email' },
            { key: 'full_name', label: 'Name' },
            { key: 'role', label: 'Role', render: (u) => <Badge color={ROLE_COLOR[u.role] || 'gray'}>{roleLabel(u.role)}</Badge> },
            ...(platform ? [{ key: 'org_id', label: 'Organization', render: (u) => orgName(u.org_id) }] : []),
            { key: 'department', label: 'Department', render: (u) => u.department || '—' },
            { key: 'is_active', label: 'Status', render: (u) => (u.is_active ? <Badge color="green">active</Badge> : <Badge color="red">deactivated</Badge>) },
            { key: 'last_login_at', label: 'Last login', render: (u) => formatDate(u.last_login_at) },
            {
              key: 'actions',
              label: '',
              render: (u) => (
                <div className="flex gap-1">
                  <Button variant="ghost" onClick={() => setForm({ ...u, full_name: u.full_name || '', department: u.department || '' })}>Edit</Button>
                  {u.auth_provider !== 'oidc' && <Button variant="ghost" onClick={() => setReset(u)}>Reset password</Button>}
                </div>
              ),
            },
          ]}
        />
      </div>
      {form && <UserForm value={form} orgs={orgs} platform={platform} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
      {orgForm && <OrgForm value={orgForm} onClose={() => setOrgForm(null)} onSaved={() => { setOrgForm(null); load(); }} />}
      {reset && <ResetPassword user={reset} onClose={() => setReset(null)} />}
    </div>
  );
}

function OrgForm({ value, onClose, onSaved }) {
  const [f, setF] = useState(value);
  const [error, setError] = useState('');
  const save = async () => {
    try {
      await api.post('/admin/orgs', f);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Modal title="Add organization" onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Short name" hint="Lowercase letters, digits and dashes, e.g. vivriti-finance.">
          <Input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase() })} />
        </Field>
        <p className="text-xs text-muted-strong">Then add an organization admin for it with “Add user”.</p>
      </div>
    </Modal>
  );
}

function UserForm({ value, orgs, platform, onClose, onSaved }) {
  const [f, setF] = useState(value);
  const [error, setError] = useState('');
  const save = async () => {
    try {
      if (f.id) {
        await api.patch(`/admin/users/${f.id}`, { full_name: f.full_name || null, role: f.role, department: f.department || null, is_active: f.is_active });
      } else {
        await api.post('/admin/users', { email: f.email, full_name: f.full_name || null, password: f.password, role: f.role, department: f.department || null, org_id: platform ? Number(f.org_id) : undefined });
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Modal title={f.id ? `Edit ${f.email}` : 'Add user'} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save}>Save</Button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        {!f.id && <Field label="Email"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>}
        <Field label="Full name"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        {!f.id && (
          <Field label="Initial password" hint="At least 12 characters with three of: lowercase, uppercase, digit, symbol. Share it securely; the user can change it.">
            <Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </Field>
        )}
        <Field label="Role" hint={ROLE_HELP[f.role]}>
          <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            {ROLES.filter((r) => platform || r !== 'platform_admin').map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
          </Select>
        </Field>
        {platform && !f.id && (
          <Field label="Organization" hint="Fixed once the user is created.">
            <Select value={f.org_id} onChange={(e) => setF({ ...f, org_id: e.target.value })}>
              {orgs.filter((o) => o.is_active).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Department"><Input value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} /></Field>
        {f.id && <Checkbox label="Active (untick to block sign-in immediately)" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />}
        {f.id && <p className="text-xs text-muted-strong">Changing role or deactivating signs the user out everywhere.</p>}
      </div>
    </Modal>
  );
}

function ResetPassword({ user, onClose }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const save = async () => {
    try {
      await api.post(`/admin/users/${user.id}/reset-password`, { password });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Modal title={`Reset password for ${user.email}`} onClose={onClose} footer={done ? <Button onClick={onClose}>Close</Button> : <><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save}>Reset</Button></>}>
      {done ? (
        <Alert kind="success">Password reset. The user's existing sessions were signed out and any lockout cleared.</Alert>
      ) : (
        <div className="space-y-3">
          <Alert>{error}</Alert>
          <Field label="New password"><Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        </div>
      )}
    </Modal>
  );
}
