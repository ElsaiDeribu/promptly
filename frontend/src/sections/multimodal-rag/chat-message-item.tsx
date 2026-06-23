import remarkGfm from 'remark-gfm';
import ReactMarkdown from 'react-markdown';

import { markdownComponents } from './markdown-components';

import type { ChatMessage } from './types';

// ----------------------------------------------------------------------

type ChatMessageItemProps = {
  message: ChatMessage;
};

function StreamingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60" />
      <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-200" />
      <span className="h-2 w-2 animate-pulse rounded-full bg-foreground/60 animation-delay-400" />
    </span>
  );
}

export default function ChatMessageItem({ message }: ChatMessageItemProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
        isUser ? 'ml-auto self-end bg-primary text-primary-foreground' : 'self-start bg-muted text-foreground'
      }`}
    >
      <div className="mb-1 text-[11px] opacity-80">{isUser ? 'You' : 'Assistant'}</div>

      <div className="break-words">
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {message.content}
          </ReactMarkdown>
        )}

        {message.isStreaming && !message.content && <StreamingDots />}
        {message.isStreaming && message.content && (
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-foreground/70" />
        )}
      </div>
    </div>
  );
}
