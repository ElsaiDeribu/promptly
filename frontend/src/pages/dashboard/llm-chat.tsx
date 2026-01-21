import { Button } from '@/components/ui/button';
import axios, { endpoints } from '@/utils/axios';
import { Textarea } from '@/components/ui/textarea';
import LoadingButton from '@/components/ui/loading-button';
import { useRef, useMemo, useState, useEffect } from 'react';
import { Card, CardTitle, CardFooter, CardHeader, CardContent, CardDescription } from '@/components/ui/card';

type ChatRole = 'system' | 'user' | 'assistant';

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

function makeId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function roleLabel(role: ChatRole) {
  if (role === 'user') return 'You';
  if (role === 'assistant') return 'Assistant';
  return 'System';
}

function roleBubbleClass(role: ChatRole) {
  switch (role) {
    case 'user':
      return 'bg-primary text-primary-foreground';
    case 'assistant':
      return 'bg-muted text-foreground';
    default:
      return 'bg-accent text-foreground';
  }
}

export default function LLMChat() {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [model, setModel] = useState<string>('');
  const [systemPrompt, setSystemPrompt] = useState<string>('You are a helpful assistant.');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const bottomRef = useRef<HTMLDivElement | null>(null);

  const requestMessages = useMemo(() => {
    const base: { role: ChatRole; content: string }[] = [];
    if (systemPrompt.trim()) base.push({ role: 'system', content: systemPrompt.trim() });
    for (const m of messages) base.push({ role: m.role, content: m.content });
    return base;
  }, [messages, systemPrompt]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    let mounted = true;

    async function loadModels() {
      try {
        const data = await axios.get(endpoints.llm.models);
        const models = (data?.data?.models ?? data?.models ?? []) as Array<{ name?: string }>;
        const names = models.map((m) => m?.name).filter(Boolean) as string[];

        if (!mounted) return;

        setAvailableModels(names);
        if (!model && names.length) setModel(names[0]);
      } catch (e: any) {
        // Non-fatal: chat can still work with an explicit model or backend default
        if (!mounted) return;
        setAvailableModels([]);
      }
    }

    loadModels();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send() {
    const text = draft.trim();
    if (!text || loading) return;

    setError('');
    setLoading(true);

    const userMessage: ChatMessage = { id: makeId(), role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    setDraft('');

    try {
      const res = await axios.post(endpoints.llm.chat, {
        model: model || undefined,
        messages: [...requestMessages, { role: 'user', content: text }],
        options: {},
      });

      const content = (res?.data?.content ?? '').toString();
      const assistantMessage: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        content: content || '(empty response)',
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (e: any) {
      const message =
        (typeof e === 'string' && e) ||
        e?.error ||
        e?.details?.error ||
        e?.details?.detail ||
        e?.message ||
        'Failed to send message';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([]);
    setError('');
  }

  return (
    <div className="p-6">
      <Card className="max-w-5xl">
        <CardHeader className="gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Chat</CardTitle>
              <CardDescription>Uses your backend endpoint at `POST /api/llm/chat`</CardDescription>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">
                Model{' '}
                <select
                  className="ml-2 h-9 rounded-md border bg-background px-2 text-sm"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={!availableModels.length}
                >
                  {availableModels.length ? (
                    availableModels.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))
                  ) : (
                    <option value="">(backend default)</option>
                  )}
                </select>
              </label>

              <Button type="button" variant="outline" onClick={clearChat}>
                Clear
              </Button>
            </div>
          </div>

          <div>
            <div className="mb-1 text-sm font-medium">System prompt</div>
            <Textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Optional system prompt..."
              className="min-h-16"
            />
          </div>
        </CardHeader>

        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <div className="h-[55vh] overflow-auto rounded-lg border bg-background p-4">
            {messages.length === 0 ? (
              <div className="text-sm text-muted-foreground">Send a message to start the conversation.</div>
            ) : (
              <div className="flex flex-col gap-3">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${roleBubbleClass(m.role)} ${
                      m.role === 'user' ? 'self-end' : 'self-start'
                    }`}
                  >
                    <div className="mb-1 text-[11px] opacity-80">{roleLabel(m.role)}</div>
                    <div className="whitespace-pre-wrap break-words">{m.content}</div>
                  </div>
                ))}
                {loading ? (
                  <div className="max-w-[85%] self-start rounded-lg bg-muted px-3 py-2 text-sm">
                    <div className="mb-1 text-[11px] opacity-80">Assistant</div>
                    Thinking…
                  </div>
                ) : null}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </CardContent>

        <CardFooter className="gap-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type your message… (Enter to send, Shift+Enter for newline)"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            className="min-h-16"
          />

          <LoadingButton type="button" loading={loading} onClick={send} className="shrink-0">
            Send
          </LoadingButton>
        </CardFooter>
      </Card>
    </div>
  );
}

