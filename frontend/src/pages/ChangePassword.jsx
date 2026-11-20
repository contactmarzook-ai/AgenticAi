import { useState } from 'react';
import api, { errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Alert, Button, Field, Input, Modal } from '../lib/ui';

export default function ChangePassword({ onClose }) {
  const setToken = useAuth((s) => s.setToken);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const save = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/auth/change-password', { current_password: current, new_password: next });
      setToken(res.data.access_token);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="Change password"
      onClose={onClose}
      footer={
        done ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={save} loading={loading} disabled={!current || !next}>Change password</Button>
          </>
        )
      }
    >
      {done ? (
        <Alert kind="success">Password changed. Other sessions have been signed out.</Alert>
      ) : (
        <div className="space-y-3">
          <Alert>{error}</Alert>
          <Field label="Current password">
            <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="New password" hint="At least 12 characters, with three of: lowercase, uppercase, digit, symbol.">
            <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
        </div>
      )}
    </Modal>
  );
}
