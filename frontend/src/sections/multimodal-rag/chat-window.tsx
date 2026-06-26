import ChatMessageItem from './chat-message-item';

import type { ChatMessage } from './types';

// ----------------------------------------------------------------------

type ChatWindowProps = {
  messages: ChatMessage[];
  bottomRef: React.RefObject<HTMLDivElement>;
};

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      <div className="text-center">
        <p className="mb-2">Upload PDFs and ask questions about them.</p>
        <p className="text-xs">
          The system will search through text, tables, and images to answer.
        </p>
      </div>
    </div>
  );
}

export default function ChatWindow({ messages, bottomRef }: ChatWindowProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain rounded-lg border bg-background p-4">
      {messages.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex flex-col gap-4">
          {messages.map((message) => (
            <ChatMessageItem key={message.id} message={message} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
