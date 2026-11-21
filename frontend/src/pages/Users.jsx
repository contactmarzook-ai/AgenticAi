import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Checkbox, Field, Input, Modal, PageHeader, Select, Table, formatDate } from '../lib/ui';

const ROLE_HELP = {
  user: 'Chat, run agents and workflows shared with them.',
  builder: 'Everything a user can, plus create agents, workflows and triggers.',
  admin: 'Everything, plus users, models, audit log and monitoring.',
};

export default function Users() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(null);
  const [reset, setReset] = useState(null);

  const load = useCallback(() => api.get('/admin/users').then((r) => setUsers(r.data)), []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Users"
        subtitle="Roles: user → builder → admin. Department controls who sees department-shared agents and workflows."
        actions={<Button icon={Plus} onClick={() => setForm({ email: '', full_name: '', password: '', role: 'user', department: '', is_active: true })}>Add user</Button>}
      />
      <div className="flex-1 overflow-y-auto p-6">
        <Table
          rows={users}
          columns={[
            { key: 'email', label: 'Email' },
            { key: 'full_name', label: 'Name' },
            { key: 'role', label: 'Role', render: (u) => <Badge color={u.role === 'admin' ? 'indigo' : u.role === 'builder' ? 'blue' : 'gray'}>{u.role}</Badge> },
            { key: 'department', label: 'Department', render: (u) => u.department || '—' },
            { key: 'is_active', label: 'Status', render: (u) => (u.is_active ? <Badge color="green">active</Badge> : <Badge color="red">deactivated</Badge>) },
            { key: 'last_login_at', label: 'Last login', render: (u) => formatDate(u.last_login_at) },
            {
              key: 'actions',
              label: '',
              render: (u) => (
                <div className="flex gap-1">
                  <Button variant="ghost" onClick={() => setForm({ ...u, full_name: u.full_name || '', department: u.department || '' })}>Edit</Button>
                  <Button variant="ghost" onClick={() => setReset(u)}>Reset password</Button>
                </div>
              ),
            },
          ]}
        />
      </div>
      {form && <UserForm value={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
      {reset && <ResetPassword user={reset} onClose={() => setReset(null)} />}
    </div>
  );
}

function UserForm({ value, onClose, onSaved }) {
  const [f, setF] = useState(value);
  const [error, setError] = useState('');
  const save = async () => {
    try {
      if (f.id) {
        await api.patch(`/admin/users/${f.id}`, { full_name: f.full_name || null, role: f.role, department: f.department || null, is_active: f.is_active });
      } else {
        await api.post('/admin/users', { email: f.email, full_name: f.full_name || null, password: f.password, role: f.role, department: f.department || null });
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
            <option value="user">user</option>
            <option value="builder">builder</option>
            <option value="admin">admin</option>
          </Select>
        </Field>
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
