import { useEffect, useState } from 'react';
import { CheckCircle2, Sparkles } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Button } from '../lib/ui';
import RunForm, { missingRequired } from './automation/RunForm';
import { ResultView } from './RunSteps';

/** A shareable form (#/f/<id>/<token>) that starts a workflow without signing in. */
export default function PublicForm({ id, token }) {
  const [form, setForm] = useState(null);
  const [values, setValues] = useState({});
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(null);
  const headers = { 'X-Form-Token': token };

  useEffect(() => {
    api.get(`/public/forms/${id}`, { headers }).then((r) => setForm(r.data)).catch((e) => setError(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, token]);

  const submit = async (e) => {
    e.preventDefault();
    const missing = missingRequired(form.fields, values);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ')}`);
      return;
    }
    setError('');
    setSending(true);
    try {
      setDone((await api.post(`/public/forms/${id}`, { input: values }, { headers })).data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <div className="mx-auto max-w-xl rounded-xl border bg-white p-8 shadow-sm">
        {!form && !error && <p className="text-sm text-gray-500">Loading…</p>}
        {!form && error && <Alert>{error}</Alert>}
        {form && !done && (
          <form onSubmit={submit} className="space-y-4">
            <h1 className="text-xl font-semibold text-gray-900">{form.title}</h1>
            {form.intro && <p className="whitespace-pre-wrap text-sm text-gray-600">{form.intro}</p>}
            {form.fields.length ? <FormFields fields={form.fields} values={values} setValues={setValues} /> : <p className="text-sm text-gray-500">Press Submit to continue.</p>}
            <Alert>{error}</Alert>
            <Button type="submit" loading={sending} className="w-full py-2">Submit</Button>
          </form>
        )}
        {done && (
          <div className="space-y-4 text-center">
            {done.status === 'failed' ? <Alert>{done.message}</Alert> : (
              <>
                <CheckCircle2 className="mx-auto h-10 w-10 text-green-600" />
                <p className="text-gray-800">{done.message}</p>
              </>
            )}
            {done.result !== undefined && done.result !== null && <div className="text-left"><ResultView value={done.result} /></div>}
            <Button variant="secondary" onClick={() => { setDone(null); setValues({}); }}>Submit another response</Button>
          </div>
        )}
      </div>
      <p className="mt-4 flex items-center justify-center gap-1 text-xs text-gray-400"><Sparkles className="h-3 w-3" /> Powered by Star Dust</p>
    </div>
  );
}

function FormFields({ fields, values, setValues }) {
  return <RunForm fields={fields} value={values} onChange={setValues} hideJson />;
}
