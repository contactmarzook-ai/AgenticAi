import { useState } from 'react';
import api, { errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { APP_NAME, Logo } from '../lib/brand';
import { Alert, Button, Field, Input } from '../lib/ui';
import StarDustScene from './StarDustScene';

export default function Login() {
  const setToken = useAuth((s) => s.setToken);
  const expired = useAuth((s) => s.expired);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/login', { email, password });
      setToken(res.data.access_token);
    } catch (err) {
      setError(errorMessage(err, 'Sign-in failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[#070b1f]">
      {/* Animated stardust: autonomous agents passing work along a flow */}
      <div className="absolute inset-0 lg:right-[480px]">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b1030] via-[#0a0f2c] to-indigo-950" />
        <StarDustScene />
        <div className="pointer-events-none absolute inset-x-0 top-0 hidden p-10 lg:block">
          <Logo size="lg" light />
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 hidden p-10 lg:block">
          <h2 className="max-w-xl text-3xl font-semibold leading-tight text-white">Autonomous agents.<br />Workflows that run themselves.</h2>
          <p className="mt-3 max-w-xl text-sm text-indigo-100/80">
            Describe what you need in plain words. {APP_NAME} turns it into AI-powered workflows that read, decide and act - on your own models, under your rules.
          </p>
        </div>
      </div>

      {/* Sign-in card */}
      <div className="relative z-10 ml-auto flex w-full items-center justify-center px-4 py-10 lg:w-[480px] lg:bg-white">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-white/10 bg-white p-8 shadow-2xl lg:border-gray-100 lg:shadow-none">
          <div className="pb-2">
            <div className="mb-6 lg:hidden"><Logo /></div>
            <h1 className="text-2xl font-semibold text-gray-900">Welcome back</h1>
            <p className="mt-1 text-sm text-gray-500">Sign in to {APP_NAME}</p>
          </div>
          {expired && !error && <Alert kind="info">Your session ended. Please sign in again.</Alert>}
          <Alert>{error}</Alert>
          <Field label="Email">
            <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" loading={loading} className="w-full py-2.5">
            Sign in
          </Button>
          <p className="text-center text-xs text-gray-400">Accounts are created by your administrator.</p>
        </form>
      </div>
    </div>
  );
}
