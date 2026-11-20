import { useState } from 'react';
import { Hexagon } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Alert, Button, Field, Input } from '../lib/ui';

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
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-lg border bg-white p-8 shadow-sm">
        <div className="flex flex-col items-center gap-2 pb-2">
          <div className="rounded-lg bg-indigo-600 p-2">
            <Hexagon className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900">Sign in to AgentOS</h1>
        </div>
        {expired && !error && <Alert kind="info">Your session ended. Please sign in again.</Alert>}
        <Alert>{error}</Alert>
        <Field label="Email">
          <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" loading={loading} className="w-full py-2">
          Sign in
        </Button>
        <p className="text-center text-xs text-gray-400">Accounts are created by your administrator.</p>
      </form>
    </div>
  );
}
