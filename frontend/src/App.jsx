import { useEffect, useState } from 'react';
import { Activity, Bot, History, KeyRound, LogOut, MessageSquare, Plug, ScrollText, Server, SlidersHorizontal, Users as UsersIcon, Workflow } from 'lucide-react';
import api, { refreshSession, signOut } from './lib/api';
import { roleLabel } from './lib/roles';
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

  // No token yet: the browser may still hold a session cookie (page reload, or back from
  // Microsoft sign-in). Try it once before showing the sign-in page.
  const [resumed, setResumed] = useState(!!token);
  useEffect(() => {
    if (!resumed) refreshSession().catch(() => {}).finally(() => setResumed(true));
  }, [resumed]);

  useEffect(() => {
    if (token && !user) {
      api.get('/auth/me').then((r) => setUser(r.data)).catch(() => logout({ expired: true }));
    }
  }, [token, user, setUser, logout]);

  if (!token && !resumed) return <div className="flex h-screen items-center justify-center text-sm text-muted-strong">Loading…</div>;
  if (!token) return <Login />;
  if (!user) return <div className="flex h-screen items-center justify-center text-sm text-muted-strong">Loading…</div>;

  const visible = PAGES.filter((p) => can(user, p.perm));
  const current = visible.find((p) => p.id === page && p.component) || visible.find((p) => p.component);
  const Page = current.component;

  return (
    <div className="flex h-screen overflow-hidden bg-app text-ink">
      <aside className="flex w-16 flex-shrink-0 flex-col bg-navy text-navy-100 md:w-60">
        <div className="flex justify-center px-3 py-5 md:justify-start md:px-5">
          <Logo light compact />
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-2 md:px-3">
          {visible.map((p) =>
            p.section ? (
              <div key={p.section} className="mx-2 border-t border-white/10 pb-1 pt-4 md:mx-0 md:border-0 md:px-3 md:pt-5">
                <span className="hidden text-[11px] font-semibold uppercase tracking-wider text-navy-200 md:inline">{p.section}</span>
              </div>
            ) : (
              <button
                key={p.id}
                onClick={() => go(p.id)}
                title={p.label}
                className={cx(
                  'flex w-full items-center justify-center gap-3 rounded-md px-3 py-2 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 md:justify-start',
                  current.id === p.id ? 'bg-brand-600 font-medium text-white shadow-sm' : 'text-navy-100 hover:bg-navy-600 hover:text-white',
                )}
              >
                <p.icon className="h-4 w-4 flex-shrink-0" />
                <span className="hidden md:inline">{p.label}</span>
              </button>
            ),
          )}
        </nav>
        <div className="border-t border-white/10 p-2 text-sm md:p-3">
          <div className="hidden truncate px-2 font-medium text-white md:block" title={user.email}>{user.full_name || user.email}</div>
          <div className="mb-2 hidden px-2 text-xs text-navy-200 md:block">
            <span>{roleLabel(user.role)}</span>
            {user.org_name ? ` · ${user.org_name}` : ''}
            {user.department ? ` · ${user.department}` : ''}
          </div>
          {user.auth_provider !== 'oidc' && <button onClick={() => setShowPassword(true)} title="Change password" className="flex w-full items-center justify-center gap-2 rounded-md px-2 py-1.5 text-navy-100 hover:bg-navy-600 hover:text-white md:justify-start">
            <KeyRound className="h-4 w-4 flex-shrink-0" /> <span className="hidden md:inline">Change password</span>
          </button>}
          <button onClick={() => confirmLeave() && signOut()} title="Sign out" className="flex w-full items-center justify-center gap-2 rounded-md px-2 py-1.5 text-red-200 hover:bg-red-500/15 hover:text-white md:justify-start">
            <LogOut className="h-4 w-4 flex-shrink-0" /> <span className="hidden md:inline">Sign out</span>
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
