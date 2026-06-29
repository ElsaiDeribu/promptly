import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Card,
  CardTitle,
  CardFooter,
  CardHeader,
  CardContent,
  CardDescription,
} from '@/components/ui/card';

import ChatWindow from './chat-window';
import MemoryPanel from './memory-panel';
import ChatComposer from './chat-composer';
import { useRagChat } from './use-rag-chat';
import DocumentUploader from './document-uploader';
import { useUserMemories } from './use-user-memories';
import { useDocumentUpload } from './use-document-upload';

// ----------------------------------------------------------------------

export default function MultimodalRagView() {
  const [draft, setDraft] = useState('');

  const memories = useUserMemories();
  const chat = useRagChat({ onComplete: memories.refresh });
  const upload = useDocumentUpload();

  const error = chat.error || upload.error || memories.error;

  function handleSelectFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    chat.setError('');
    upload.selectFile(file);
  }

  async function handleUploadAndProcess() {
    chat.setError('');
    await upload.uploadSelectedFile();
  }

  async function handleSend() {
    const text = draft.trim();
    if (!text || chat.loading) return;

    setDraft('');
    await chat.sendMessage(text);
  }

  function handleClear() {
    chat.clearChat();
    upload.resetFeedback();
  }

  return (
    <div className="flex justify-center">
      <Card className="flex h-[calc(100dvh-6.5rem)] w-full max-w-7xl flex-col gap-4 overflow-hidden py-4">
        <CardHeader className="shrink-0 gap-3 pb-0">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Multimodal RAG</CardTitle>
              <CardDescription>
                Upload PDFs with text, tables, and images. Ask questions about them. The
                assistant remembers your preferences across chats.
              </CardDescription>
            </div>

            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={handleClear}>
                Clear Chat
              </Button>
            </div>
          </div>

          <Separator />
        </CardHeader>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row">
          <aside className="flex w-full shrink-0 flex-col gap-4 border-b p-4 md:min-h-0 md:w-72 md:shrink md:overflow-hidden md:border-b-0 md:border-r lg:w-80">
            <div className="shrink-0">
              <DocumentUploader
                uploading={upload.uploading}
                hasSelectedFile={Boolean(upload.selectedFile)}
                successMessage={upload.successMessage}
                documents={upload.documents}
                fileInputRef={upload.fileInputRef}
                onSelectFile={handleSelectFile}
                onBrowse={upload.openFilePicker}
                onUploadAndProcess={handleUploadAndProcess}
                onGenerateEvalExamples={upload.generateEvalExamples}
              />
            </div>

            <MemoryPanel
              className="max-h-48 min-h-0 overflow-hidden md:max-h-none md:flex-1"
              memories={memories.memories}
              loading={memories.loading}
              onDelete={memories.deleteMemory}
              onRefresh={memories.refresh}
            />
          </aside>

          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
            <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {error ? (
                <div className="mb-4 shrink-0 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              ) : null}

              <ChatWindow messages={chat.messages} bottomRef={chat.bottomRef} />
            </CardContent>

            <CardFooter className="shrink-0 gap-2 border-t pt-4">
              <ChatComposer
                value={draft}
                loading={chat.loading}
                disabled={upload.uploading}
                onChange={setDraft}
                onSubmit={handleSend}
              />
            </CardFooter>
          </div>
        </div>
      </Card>
    </div>
  );
}
