import { endpoints } from '@/utils/axios';
import { HOST_API } from '@/config-global';
import { useRef, useState, useEffect, useCallback } from 'react';

import { makeId, CHAT_WINDOW_SIZE, resolveErrorMessage } from './utils';

import type { ChatMessage } from './types';

// ----------------------------------------------------------------------

const SSE_PREFIX = 'data: ';

type UseRagChatReturn = {
  messages: ChatMessage[];
  loading: boolean;
  error: string;
  bottomRef: React.RefObject<HTMLDivElement>;
  sendMessage: (question: string) => Promise<void>;
  clearChat: () => void;
  setError: (message: string) => void;
};

/**
 * Owns the streaming RAG conversation: it appends the user message, opens an
 * SSE stream against the backend, and incrementally updates the assistant
 * message as tokens arrive. Aborts any in-flight request on unmount.
 */
export function useRagChat(): UseRagChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    []
  );

  const appendAssistantToken = useCallback((assistantId: string, token: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m))
    );
  }, []);

  const finishStreaming = useCallback((assistantId: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
    );
  }, []);

  const sendMessage = useCallback(
    async (question: string) => {
      const text = question.trim();
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

      const messageWindow = [...messages, userMessage]
        .filter((m) => m.content.trim() && !m.isStreaming)
        .slice(-CHAT_WINDOW_SIZE)
        .map(({ role, content }) => ({ role, content }));

      setMessages((prev) => [...prev, userMessage, assistantMessage]);

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
          body: JSON.stringify({ messages: messageWindow }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody?.error || errBody?.detail || `HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
           
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith(SSE_PREFIX)) continue;

            const payload = JSON.parse(line.slice(SSE_PREFIX.length));

            if (payload.token) {
              appendAssistantToken(assistantId, payload.token);
            } else if (payload.error) {
              setError(payload.error);
            }
          }
        }

        finishStreaming(assistantId);
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        setError(resolveErrorMessage(e, 'Failed to send message'));
      } finally {
        abortRef.current = null;
        setLoading(false);
      }
    },
    [loading, messages, appendAssistantToken, finishStreaming]
  );

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError('');
  }, []);

  return { messages, loading, error, bottomRef, sendMessage, clearChat, setError };
}
