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
import ChatComposer from './chat-composer';
import { useRagChat } from './use-rag-chat';
import DocumentUploader from './document-uploader';
import { useDocumentUpload } from './use-document-upload';

// ----------------------------------------------------------------------

export default function MultimodalRagView() {
  const [draft, setDraft] = useState('');

  const chat = useRagChat();
  const upload = useDocumentUpload();

  const error = chat.error || upload.error;

  async function handleSelectFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    chat.setError('');
    await upload.uploadFile(file);
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
      <Card className="w-full max-w-5xl">
        <CardHeader className="gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Multimodal RAG</CardTitle>
              <CardDescription>
                Upload PDFs with text, tables, and images. Ask questions about them.
              </CardDescription>
            </div>

            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={handleClear}>
                Clear Chat
              </Button>
            </div>
          </div>

          <Separator />

          <DocumentUploader
            uploading={upload.uploading}
            successMessage={upload.successMessage}
            documents={upload.documents}
            fileInputRef={upload.fileInputRef}
            onSelectFile={handleSelectFile}
            onBrowse={upload.openFilePicker}
          />
        </CardHeader>

        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <ChatWindow messages={chat.messages} bottomRef={chat.bottomRef} />
        </CardContent>

        <CardFooter className="gap-2">
          <ChatComposer
            value={draft}
            loading={chat.loading}
            disabled={upload.uploading}
            onChange={setDraft}
            onSubmit={handleSend}
          />
        </CardFooter>
      </Card>
    </div>
  );
}
