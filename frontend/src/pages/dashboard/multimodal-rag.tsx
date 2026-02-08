import { Button } from '@/components/ui/button';
import axios, { endpoints } from '@/utils/axios';
import { Textarea } from '@/components/ui/textarea';
import LoadingButton from '@/components/ui/loading-button';
import { useRef, useState, useEffect } from 'react';
import { Card, CardTitle, CardFooter, CardHeader, CardContent, CardDescription } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  context?: {
    texts?: string[];
    images?: string[];
  };
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

  async function send() {
    const text = draft.trim();
    if (!text || loading) return;

    setError('');
    setLoading(true);

    const userMessage: ChatMessage = { id: makeId(), role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    setDraft('');

    try {
      const res = await axios.post(endpoints.llm.ragQuery, {
        question: text,
      });

      const answer = res?.data?.answer || '(empty response)';
      const context = res?.data?.context || {};
      
      const assistantMessage: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        content: answer,
        context: context,
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
          <div className="rounded-lg border bg-muted/30 p-4">
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
                <div className="mb-1 text-xs font-medium text-muted-foreground">Processed Files:</div>
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
                  <p className="text-xs">The system will search through text, tables, and images to answer.</p>
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
                      <div className="whitespace-pre-wrap break-words">{m.content}</div>
                    </div>

                    {/* Display context images if available */}
                    {m.role === 'assistant' && m.context?.images && m.context.images.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2 pl-2">
                        {m.context.images.map((imgUrl, idx) => (
                          <div key={idx} className="overflow-hidden rounded-md border">
                            <img
                              src={imgUrl}
                              alt={`Context ${idx + 1}`}
                              className="h-32 w-auto object-contain"
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display = 'none';
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {loading ? (
                  <div className="max-w-[85%] self-start rounded-lg bg-muted px-3 py-2 text-sm">
                    <div className="mb-1 text-[11px] opacity-80">Assistant</div>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 animate-pulse rounded-full bg-foreground/60" />
                      <div className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-200" />
                      <div className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-400" />
                    </div>
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
