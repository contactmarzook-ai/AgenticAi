import { useEffect, useState } from 'react';
import { Activity, Bot, History, KeyRound, LogOut, MessageSquare, Plug, ScrollText, Server, SlidersHorizontal, Users as UsersIcon, Workflow } from 'lucide-react';
import api from './lib/api';
import { can, useAuth } from './lib/auth';
import { cx } from './lib/ui';
import Login from './pages/Login';
import Chat from './pages/Chat';
import Agents from './pages/Agents';
import Automations from './pages/Automations';
import Connections from './pages/Connections';
import Settings from './pages/Settings';
import Runs from './pages/Runs';
import Models from './pages/Models';
import Users from './pages/Users';
import Audit from './pages/Audit';
import Monitoring from './pages/Monitoring';
import ChangePassword from './pages/ChangePassword';
import PublicForm from './pages/PublicForm';
import { Logo } from './lib/brand';
import { confirmLeave } from './lib/unsaved';

const PAGES = [
  { id: 'workflows', label: 'Workflows', icon: Workflow, perm: 'workflow:read', component: Automations },
  { id: 'chat', label: 'Chat', icon: MessageSquare, perm: 'chat:use', component: Chat },
  { id: 'runs', label: 'History', icon: History, perm: 'run:read_own', component: Runs },
  { id: 'agents', label: 'Agents', icon: Bot, perm: 'agent:read', component: Agents },
  { id: 'connections', label: 'Connections', icon: Plug, perm: 'workflow:write', component: Connections },
  { section: 'Administration', perm: 'user:manage' },
  { id: 'settings', label: 'Settings', icon: SlidersHorizontal, perm: 'settings:manage', component: Settings },
  { id: 'monitoring', label: 'Monitoring', icon: Activity, perm: 'monitoring:read', component: Monitoring },
  { id: 'models', label: 'Models', icon: Server, perm: 'model:manage', component: Models },
  { id: 'users', label: 'Users', icon: UsersIcon, perm: 'user:manage', component: Users },
  { id: 'audit', label: 'Audit log', icon: ScrollText, perm: 'audit:read', component: Audit },
];

function usePage() {
  const read = () => window.location.hash.replace('#/', '').split('?')[0].split('/')[0].replace(/^automations$/, 'workflows') || 'workflows';
  const [page, setPage] = useState(read);
  useEffect(() => {
    const onHash = () => setPage(read());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  return [page, (p) => {
    if (!confirmLeave()) return;
    // Clicking the page you are on goes back to its start (e.g. leaves the workflow builder).
    if (p === read()) window.dispatchEvent(new Event('stardust:home'));
    else window.location.hash = `#/${p}`;
  }];
}

export default function App() {
  const publicForm = window.location.hash.match(/^#\/f\/(\d+)\/([\w-]+)/);
  if (publicForm) return <PublicForm id={publicForm[1]} token={publicForm[2]} />;
  return <SignedInApp />;
}

function SignedInApp() {
  const { token, user, setUser, logout } = useAuth();
  const [page, go] = usePage();
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (token && !user) {
      api.get('/auth/me').then((r) => setUser(r.data)).catch(() => logout({ expired: true }));
    }
  }, [token, user, setUser, logout]);

  if (!token) return <Login />;
  if (!user) return <div className="flex h-screen items-center justify-center text-sm text-gray-500">Loading…</div>;

  const visible = PAGES.filter((p) => can(user, p.perm));
  const current = visible.find((p) => p.id === page && p.component) || visible.find((p) => p.component);
  const Page = current.component;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <aside className="flex w-56 flex-shrink-0 flex-col border-r bg-white">
        <div className="px-4 py-4">
          <Logo />
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
          {visible.map((p) =>
            p.section ? (
              <div key={p.section} className="px-2 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-gray-400">
                {p.section}
              </div>
            ) : (
              <button
                key={p.id}
                onClick={() => go(p.id)}
                className={cx(
                  'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm',
                  current.id === p.id ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-gray-600 hover:bg-gray-50',
                )}
              >
                <p.icon className="h-4 w-4" />
                {p.label}
              </button>
            ),
          )}
        </nav>
        <div className="border-t p-3 text-sm">
          <div className="truncate font-medium text-gray-800" title={user.email}>{user.full_name || user.email}</div>
          <div className="mb-2 text-xs text-gray-500">
            <span className="capitalize">{user.role}</span>
            {user.department ? ` · ${user.department}` : ''}
          </div>
          <button onClick={() => setShowPassword(true)} className="flex w-full items-center gap-2 rounded px-1 py-1 text-gray-600 hover:bg-gray-50">
            <KeyRound className="h-4 w-4" /> Change password
          </button>
          <button onClick={() => confirmLeave() && logout()} className="flex w-full items-center gap-2 rounded px-1 py-1 text-red-600 hover:bg-red-50">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Page user={user} />
      </main>
      {showPassword && <ChangePassword onClose={() => setShowPassword(false)} />}
    </div>
  );
}
