import axios, { endpoints } from '@/utils/axios';
import { useRef, useState, useEffect, useCallback } from 'react';

import { resolveErrorMessage } from '../multimodal-rag/utils';
import { mapDocumentFromApi } from './document-utils';

import type { DocumentDetailResponse, TrackedDocument } from '../multimodal-rag/types';

// ----------------------------------------------------------------------

const POLL_INTERVALS_MS = [30_000, 60_000, 120_000];
const MAX_POLL_INTERVAL_MS = 120_000;
const MAX_POLL_DURATION_MS = 60 * 60 * 1000;

function getPollIntervalMs(scheduleIndex: number): number {
  return scheduleIndex < POLL_INTERVALS_MS.length
    ? POLL_INTERVALS_MS[scheduleIndex]
    : MAX_POLL_INTERVAL_MS;
}

type UseDocumentsOptions = {
  autoFetch?: boolean;
};

export type UseDocumentsReturn = {
  documents: TrackedDocument[];
  loading: boolean;
  error: string;
  refreshDocuments: () => Promise<void>;
  deleteDocument: (documentId: string) => Promise<void>;
  updateDocument: (id: string, patch: Partial<TrackedDocument>) => void;
  addDocument: (doc: TrackedDocument) => void;
  startPolling: (documentId: string) => void;
  stopPolling: (documentId: string) => void;
  setError: (message: string) => void;
};

export function useDocuments(options: UseDocumentsOptions = {}): UseDocumentsReturn {
  const { autoFetch = true } = options;

  const [documents, setDocuments] = useState<TrackedDocument[]>([]);
  const [loading, setLoading] = useState(autoFetch);
  const [error, setError] = useState('');

  const pollTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(
    () => () => {
      Object.values(pollTimers.current).forEach(clearTimeout);
      pollTimers.current = {};
    },
    []
  );

  const updateDocument = useCallback((id: string, patch: Partial<TrackedDocument>) => {
    setDocuments((prev) => prev.map((doc) => (doc.id === id ? { ...doc, ...patch } : doc)));
  }, []);

  const stopPolling = useCallback((documentId: string) => {
    const timer = pollTimers.current[documentId];
    if (timer) {
      clearTimeout(timer);
      delete pollTimers.current[documentId];
    }
  }, []);

  const startPolling = useCallback(
    (documentId: string) => {
      stopPolling(documentId);

      const startedAt = Date.now();
      let scheduleIndex = 0;

      const scheduleNext = () => {
        if (Date.now() - startedAt >= MAX_POLL_DURATION_MS) {
          delete pollTimers.current[documentId];
          return;
        }

        const delay = getPollIntervalMs(scheduleIndex);
        scheduleIndex += 1;
        pollTimers.current[documentId] = setTimeout(tick, delay);
      };

      const tick = async () => {
        try {
          const { data } = await axios.get<DocumentDetailResponse>(
            endpoints.llm.documentDetail(documentId)
          );

          updateDocument(documentId, {
            status: data.status,
            errorMessage: data.error_message || undefined,
            evalGenerationStatus: data.eval_generation_status,
            evalExampleCount: data.eval_example_count,
            layoutGenerationStatus: data.layout_generation_status,
            outlineGenerationStatus: data.outline_generation_status,
          });

          if (data.status === 'processed' || data.status === 'failed') {
            delete pollTimers.current[documentId];
            return;
          }
        } catch {
          // Keep polling on transient errors.
        }

        scheduleNext();
      };

      scheduleNext();
    },
    [stopPolling, updateDocument]
  );

  const refreshDocuments = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await axios.get<DocumentDetailResponse[]>(endpoints.llm.documents);
      const mapped = data.map(mapDocumentFromApi);
      setDocuments(mapped);

      for (const doc of mapped) {
        if (doc.status !== 'processed' && doc.status !== 'failed') {
          startPolling(doc.id);
        }
      }
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to load documents'));
    } finally {
      setLoading(false);
    }
  }, [startPolling]);

  useEffect(() => {
    if (autoFetch) {
      refreshDocuments();
    }
  }, [autoFetch, refreshDocuments]);

  const addDocument = useCallback(
    (doc: TrackedDocument) => {
      setDocuments((prev) => {
        if (prev.some((existing) => existing.id === doc.id)) {
          return prev.map((existing) => (existing.id === doc.id ? { ...existing, ...doc } : existing));
        }
        return [doc, ...prev];
      });
    },
    []
  );

  const deleteDocument = useCallback(
    async (documentId: string) => {
      setError('');
      stopPolling(documentId);
      try {
        await axios.delete(endpoints.llm.documentDetail(documentId));
        setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to delete document'));
        throw e;
      }
    },
    [stopPolling]
  );

  return {
    documents,
    loading,
    error,
    refreshDocuments,
    deleteDocument,
    updateDocument,
    addDocument,
    startPolling,
    stopPolling,
    setError,
  };
}
