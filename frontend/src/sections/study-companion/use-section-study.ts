import { endpoints } from '@/utils/axios';
import { HOST_API } from '@/config-global';
import { useCallback, useRef, useState } from 'react';

import { makeId, CHAT_WINDOW_SIZE, resolveErrorMessage } from '../multimodal-rag/utils';

import type { ChatMessage, StudyQuestion, StudySection } from './types';

// ----------------------------------------------------------------------

const SSE_PREFIX = 'data: ';

type UseSectionStudyOptions = {
  documentId: string;
  section: StudySection | null;
  scope: import('./section-scope').SectionStudyScope | null;
  filename: string;
};

type UseSectionStudyReturn = {
  notes: string;
  notesLoading: boolean;
  questions: StudyQuestion[];
  questionsLoading: boolean;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  error: string;
  generateNotes: (force?: boolean) => Promise<void>;
  generateQuestions: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  clearChat: () => void;
};

export function useSectionStudy({
  documentId,
  section,
  scope,
  filename,
}: UseSectionStudyOptions): UseSectionStudyReturn {
  const [notes, setNotes] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);
  const [questions, setQuestions] = useState<StudyQuestion[]>([]);
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const sectionContext = section
    ? `Section: ${section.title} (pages ${scope?.pageStart ?? section.page_start}–${scope?.pageEnd ?? section.page_end}${scope?.includesChildren ? ', including all subsections' : ''})`
    : '';

  const generateNotes = useCallback(
    async (force = false): Promise<string | null> => {
      if (!section) return null;
      setNotesLoading(true);
      setError('');
      try {
        const token = sessionStorage.getItem('accessToken');
        const res = await fetch(
          `${HOST_API}${endpoints.llm.sectionNotes(documentId, section.id)}`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ force }),
          }
        );
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody?.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const generated = data.notes || '';
        setNotes(generated);
        return generated;
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to generate notes'));
        return null;
      } finally {
        setNotesLoading(false);
      }
    },
    [documentId, section]
  );

  const generateQuestions = useCallback(async () => {
    if (!section) return;
    setQuestionsLoading(true);
    setError('');
    try {
      const token = sessionStorage.getItem('accessToken');
      const res = await fetch(
        `${HOST_API}${endpoints.llm.sectionQuestions(documentId, section.id)}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ count: 5 }),
        }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setQuestions(data.questions || []);
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to generate questions'));
    } finally {
      setQuestionsLoading(false);
    }
  }, [documentId, section]);

  const sendMessage = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || chatLoading || !section) return;

      setError('');
      setChatLoading(true);

      const userMessage: ChatMessage = { id: makeId(), role: 'user', content: question };
      const assistantId = makeId();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        isStreaming: true,
      };

      const messageWindow = [...chatMessages, userMessage]
        .filter((m) => m.content.trim() && !m.isStreaming)
        .slice(-CHAT_WINDOW_SIZE)
        .map(({ role, content }) => ({ role, content }));

      setChatMessages((prev) => [...prev, userMessage, assistantMessage]);

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
          body: JSON.stringify({
            messages: messageWindow,
            document_id: Number(documentId),
            section_context: `Document: ${filename}\n${sectionContext}`,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody?.error || `HTTP ${res.status}`);
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
              setChatMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: m.content + payload.token } : m
                )
              );
            } else if (payload.error) {
              setError(payload.error);
            }
          }
        }

        setChatMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
        );
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        setError(resolveErrorMessage(e, 'Failed to send message'));
      } finally {
        abortRef.current = null;
        setChatLoading(false);
      }
    },
    [chatLoading, chatMessages, documentId, filename, section, scope, sectionContext]
  );

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setChatMessages([]);
  }, []);

  const loadCachedNotes = useCallback((cachedNotes: string) => {
    setNotes(cachedNotes);
  }, []);

  const resetSection = useCallback(() => {
    setNotes('');
    setQuestions([]);
    clearChat();
    setError('');
  }, [clearChat]);

  return {
    notes,
    notesLoading,
    questions,
    questionsLoading,
    chatMessages,
    chatLoading,
    error,
    generateNotes,
    generateQuestions,
    sendMessage,
    clearChat,
    loadCachedNotes,
    resetSection,
  };
}
