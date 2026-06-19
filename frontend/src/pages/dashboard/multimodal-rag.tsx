import type { Components } from 'react-markdown';

import remarkGfm from 'remark-gfm';
import { HOST_API } from '@/config-global';
import ReactMarkdown from 'react-markdown';
import { Button } from '@/components/ui/button';
import axios, { endpoints } from '@/utils/axios';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import LoadingButton from '@/components/ui/loading-button';
import { useRef, useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardTitle,
  CardFooter,
  CardHeader,
  CardContent,
  CardDescription,
} from '@/components/ui/card';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
};

const markdownComponents: Components = {
  p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
  h1: ({ children }) => <h1 className="mt-3 mb-1.5 text-lg font-bold">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-3 mb-1.5 text-base font-bold">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-2 mb-1 text-sm font-semibold">{children}</h3>,
  ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <code
          className={`block my-2 overflow-x-auto rounded-md bg-black/5 p-3 text-xs dark:bg-white/10 ${className || ''}`}
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-black/10 px-1 py-0.5 text-xs dark:bg-white/10" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-foreground/30 pl-3 italic opacity-80">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted px-2 py-1 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-3 border-border" />,
};

function makeId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function MultimodalRAG() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string>('');
  const [uploadSuccess, setUploadSuccess] = useState<string>('');
  const [processedFiles, setProcessedFiles] = useState<string[]>([]);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [messages, loading]);

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF file');
      return;
    }

    setError('');
    setUploadSuccess('');
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await axios.post(endpoints.llm.ragProcess, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setUploadSuccess(`Successfully processed: ${res.data.filename || file.name}`);
      setProcessedFiles((prev) => [...prev, res.data.filename || file.name]);

      // Clear the file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (e: any) {
      const message =
        (typeof e === 'string' && e) ||
        e?.error ||
        e?.details ||
        e?.message ||
        'Failed to upload and process PDF';
      setError(message);
    } finally {
      setUploading(false);
    }
  }

  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || loading) return;

    setError('');
    setLoading(true);

    const userMessage: ChatMessage = { id: makeId(), role: 'user', content: text };
    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setDraft('');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = sessionStorage.getItem('accessToken');
      const res = await fetch(`${HOST_API}${endpoints.llm.ragQueryStream}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: text }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.error || errBody?.detail || `HTTP ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          const payload = JSON.parse(line.slice(6));

          if (payload.token) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + payload.token } : m
              )
            );
          } else if (payload.error) {
            setError(payload.error);
          }
        }
      }

      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
      );
    } catch (e: any) {
      if (e.name === 'AbortError') return;
      const message =
        (typeof e === 'string' && e) || e?.error || e?.message || 'Failed to send message';
      setError(message);
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  }, [draft, loading]);

  function clearChat() {
    setMessages([]);
    setError('');
  }

  return (
    <div className="flex justify-center">
      <Card className="max-w-5xl w-full">
        <CardHeader className="gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Multimodal RAG</CardTitle>
              <CardDescription>
                Upload PDFs with text, tables, and images. Ask questions about them.
              </CardDescription>
            </div>

            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={clearChat}>
                Clear Chat
              </Button>
            </div>
          </div>

          <Separator />

          {/* File Upload Section */}
          <div className="rounded-lg border bg-muted/30 p-2">
            <div className="mb-2 text-sm font-medium">Upload PDF Documents</div>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                onChange={handleFileUpload}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                disabled={uploading}
              />
              <LoadingButton
                type="button"
                loading={uploading}
                onClick={() => fileInputRef.current?.click()}
                variant="secondary"
                className="shrink-0"
              >
                {uploading ? 'Processing...' : 'Browse'}
              </LoadingButton>
            </div>

            {uploadSuccess && (
              <div className="mt-2 rounded-md border border-green-600/40 bg-green-50 p-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
                {uploadSuccess}
              </div>
            )}

            {processedFiles.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 text-xs font-medium text-muted-foreground">
                  Processed Files:
                </div>
                <div className="flex flex-wrap gap-1">
                  {processedFiles.map((file, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center rounded-full bg-primary/10 px-2 py-1 text-xs text-primary"
                    >
                      {file}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CardHeader>

        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <div className="h-[50vh] overflow-auto rounded-lg border bg-background p-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                <div className="text-center">
                  <p className="mb-2">Upload PDFs and ask questions about them.</p>
                  <p className="text-xs">
                    The system will search through text, tables, and images to answer.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {messages.map((m) => (
                  <div key={m.id}>
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                        m.role === 'user'
                          ? 'self-end bg-primary text-primary-foreground'
                          : 'self-start bg-muted text-foreground'
                      } ${m.role === 'user' ? 'ml-auto' : ''}`}
                    >
                      <div className="mb-1 text-[11px] opacity-80">
                        {m.role === 'user' ? 'You' : 'Assistant'}
                      </div>
                      <div className="break-words">
                        {m.role === 'assistant' ? (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={markdownComponents}
                          >
                            {m.content}
                          </ReactMarkdown>
                        ) : (
                          <span className="whitespace-pre-wrap">{m.content}</span>
                        )}
                        {m.isStreaming && !m.content && (
                          <span className="inline-flex items-center gap-1">
                            <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60" />
                            <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-200" />
                            <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-400" />
                          </span>
                        )}
                        {m.isStreaming && m.content && (
                          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-foreground/70" />
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </CardContent>

        <CardFooter className="gap-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask a question about your documents... (Enter to send, Shift+Enter for newline)"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            className="min-h-16"
            disabled={loading || uploading}
          />

          <LoadingButton
            type="button"
            loading={loading}
            onClick={send}
            className="shrink-0"
            disabled={uploading}
          >
            Send
          </LoadingButton>
        </CardFooter>
      </Card>
    </div>
  );
}
