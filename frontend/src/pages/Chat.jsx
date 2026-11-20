import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, Loader2, Plus, Send, Trash2, User as UserIcon } from 'lucide-react';
import api, { errorMessage } from '../lib/api';
import { Alert, Badge, Button, Modal, Select, cx } from '../lib/ui';
import RunSteps from './RunSteps';

const ROUTING_LABEL = { keyword: 'keyword match', llm: 'AI routed', general: 'general assistant', pinned: 'pinned agent' };

export default function Chat() {
  const [sessions, setSessions] = useState([]);
  const [agents, setAgents] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [newAgent, setNewAgent] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [runDetail, setRunDetail] = useState(null);
  const bottom = useRef(null);

  const loadSessions = useCallback(() => api.get('/chat/sessions').then((r) => setSessions(r.data)), []);

  useEffect(() => {
    loadSessions();
    api.get('/agents').then((r) => setAgents(r.data)).catch(() => {});
  }, [loadSessions]);

  const openSession = (s) => {
    setActive(s);
    setMessages([]);
    if (s) api.get(`/chat/sessions/${s.id}/messages`).then((r) => setMessages(r.data));
  };

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const send = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setError('');
    setSending(true);
    setInput('');
    let session = active;
    try {
      if (!session) {
        const title = text.length > 40 ? text.slice(0, 40) + '…' : text;
        session = (await api.post('/chat/sessions', { title, agent_id: newAgent ? Number(newAgent) : null })).data;
        setActive(session);
      }
      setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: 'user', content: text }]);
      const reply = (await api.post(`/chat/sessions/${session.id}/messages`, { message: text })).data;
      const all = (await api.get(`/chat/sessions/${session.id}/messages`)).data;
      setMessages(all.length ? all : (m) => [...m, reply]);
      loadSessions();
    } catch (err) {
      setError(errorMessage(err));
      setInput(text);
    } finally {
      setSending(false);
    }
  };

  const remove = async (s, e) => {
    e.stopPropagation();
    if (!confirm(`Delete chat "${s.title}"?`)) return;
    await api.delete(`/chat/sessions/${s.id}`);
    if (active?.id === s.id) openSession(null);
    loadSessions();
  };

  const openRun = async (runId) => setRunDetail((await api.get(`/runs/${runId}`)).data);

  const pinned = active?.agent_id ? agents.find((a) => a.id === active.agent_id) : null;

  return (
    <div className="flex h-full">
      <div className="flex w-64 flex-shrink-0 flex-col border-r bg-white">
        <div className="p-3">
          <Button icon={Plus} className="w-full" onClick={() => openSession(null)}>
            New chat
          </Button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => openSession(s)}
              className={cx(
                'group flex cursor-pointer items-center justify-between rounded-md px-2.5 py-2 text-sm',
                active?.id === s.id ? 'bg-gray-100 font-medium' : 'text-gray-600 hover:bg-gray-50',
              )}
            >
              <span className="truncate">{s.title}</span>
              <button onClick={(e) => remove(s, e)} className="p-0.5 text-gray-400 opacity-0 hover:text-red-500 group-hover:opacity-100" aria-label="Delete chat">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b bg-white px-6 py-3">
          {active ? (
            <>
              <h1 className="truncate font-medium text-gray-900">{active.title}</h1>
              {pinned && <Badge color="indigo">agent: {pinned.name}</Badge>}
            </>
          ) : (
            <>
              <h1 className="font-medium text-gray-900">New chat</h1>
              <Select value={newAgent} onChange={(e) => setNewAgent(e.target.value)} className="ml-auto max-w-xs">
                <option value="">Auto-route to the best agent</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    Talk to: {a.name}
                  </option>
                ))}
              </Select>
            </>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {!messages.length && !sending && (
              <div className="py-16 text-center text-gray-500">
                <Bot className="mx-auto mb-3 h-10 w-10 text-gray-300" />
                <p>Ask a question. Requests are routed to the agent or workflow that fits, or answered directly.</p>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={cx('flex gap-3', m.role === 'user' && 'flex-row-reverse')}>
                <div className={cx('flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full', m.role === 'user' ? 'bg-gray-200' : 'bg-indigo-100')}>
                  {m.role === 'user' ? <UserIcon className="h-4 w-4 text-gray-600" /> : <Bot className="h-4 w-4 text-indigo-600" />}
                </div>
                <div className={cx('max-w-[80%] rounded-lg px-4 py-2.5 text-sm', m.role === 'user' ? 'bg-indigo-600 text-white' : 'border bg-white text-gray-800')}>
                  <div className="whitespace-pre-wrap break-words">{m.content}</div>
                  {m.role === 'assistant' && m.metadata_json && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t pt-2 text-xs text-gray-500">
                      {m.metadata_json.routing?.method && <Badge>{ROUTING_LABEL[m.metadata_json.routing.method] || m.metadata_json.routing.method}</Badge>}
                      {m.metadata_json.target && (
                        <Badge color="indigo">
                          {m.metadata_json.target.type}: {m.metadata_json.target.name}
                        </Badge>
                      )}
                      {m.metadata_json.model && <Badge>{m.metadata_json.model}</Badge>}
                      {m.run_id && (
                        <button className="text-indigo-600 hover:underline" onClick={() => openRun(m.run_id)}>
                          view steps
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" /> Working…
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <form onSubmit={send} className="border-t bg-white px-6 py-4">
          <div className="mx-auto max-w-3xl space-y-2">
            <Alert>{error}</Alert>
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) send(e);
                }}
                rows={1}
                placeholder="Message…  (Shift+Enter for a new line)"
                className="flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <Button type="submit" icon={Send} loading={sending} disabled={!input.trim()}>
                Send
              </Button>
            </div>
          </div>
        </form>
      </div>

      {runDetail && (
        <Modal wide title={`Run #${runDetail.id} · ${runDetail.target_type} ${runDetail.target_name}`} onClose={() => setRunDetail(null)}>
          <p className="mb-3 text-xs text-gray-500">
            {runDetail.model_name && <>model {runDetail.model_name} · </>}
            {runDetail.llm_calls} LLM calls · {runDetail.prompt_tokens + runDetail.completion_tokens} tokens
          </p>
          <RunSteps steps={runDetail.steps} />
        </Modal>
      )}
    </div>
  );
}
