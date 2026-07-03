import axios, { endpoints } from '@/utils/axios';
import { useCallback, useState } from 'react';

import { resolveErrorMessage } from './utils';

import type { DocumentLayout, DocumentLayoutResponse, GenerateDocumentLayoutResponse } from './types';

// ----------------------------------------------------------------------

const LAYOUT_POLL_INTERVAL_MS = 3000;
const LAYOUT_POLL_TIMEOUT_MS = 20 * 60 * 1000;

type UseDocumentLayoutReturn = {
  layout: DocumentLayout | null;
  loading: boolean;
  error: string;
  status: DocumentLayoutResponse['layout_generation_status'] | null;
  openLayout: (documentId: string, filename: string) => Promise<'completed' | 'failed' | null>;
  regenerateLayout: () => Promise<void>;
  reset: () => void;
  activeDocumentId: string | null;
  activeFilename: string | null;
};

export function useDocumentLayout(): UseDocumentLayoutReturn {
  const [layout, setLayout] = useState<DocumentLayout | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<DocumentLayoutResponse['layout_generation_status'] | null>(
    null
  );
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [activeFilename, setActiveFilename] = useState<string | null>(null);

  const pollLayout = useCallback(async (documentId: string) => {
    const startedAt = Date.now();

    while (Date.now() - startedAt < LAYOUT_POLL_TIMEOUT_MS) {
      const { data } = await axios.get<DocumentLayoutResponse>(
        endpoints.llm.documentLayout(documentId)
      );

      setStatus(data.layout_generation_status);

      if (data.layout_generation_status === 'completed' && data.layout) {
        setLayout(data.layout);
        return;
      }

      if (data.layout_generation_status === 'failed') {
        throw new Error(data.layout_error_message || 'Layout extraction failed');
      }

      await new Promise((resolve) => setTimeout(resolve, LAYOUT_POLL_INTERVAL_MS));
    }

    throw new Error('Timed out waiting for layout extraction');
  }, []);

  const fetchOrGenerate = useCallback(
    async (documentId: string, force = false): Promise<'completed' | 'failed' | null> => {
      setLoading(true);
      setError('');
      setLayout(null);

      try {
        const { data, status: httpStatus } = await axios.post<GenerateDocumentLayoutResponse>(
          endpoints.llm.generateDocumentLayout(documentId),
          { force }
        );

        setStatus(data.layout_generation_status);

        if (data.layout) {
          setLayout(data.layout);
          return 'completed';
        }

        if (httpStatus === 202 || data.layout_generation_status === 'processing') {
          await pollLayout(documentId);
          return 'completed';
        }

        if (data.layout_generation_status === 'failed') {
          throw new Error('Layout extraction failed');
        }

        return null;
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to load document layout'));
        return 'failed';
      } finally {
        setLoading(false);
      }
    },
    [pollLayout]
  );

  const openLayout = useCallback(
    async (documentId: string, filename: string) => {
      setActiveDocumentId(documentId);
      setActiveFilename(filename);
      return fetchOrGenerate(documentId, false);
    },
    [fetchOrGenerate]
  );

  const regenerateLayout = useCallback(async () => {
    if (!activeDocumentId) return;
    await fetchOrGenerate(activeDocumentId, true);
  }, [activeDocumentId, fetchOrGenerate]);

  const reset = useCallback(() => {
    setLayout(null);
    setLoading(false);
    setError('');
    setStatus(null);
    setActiveDocumentId(null);
    setActiveFilename(null);
  }, []);

  return {
    layout,
    loading,
    error,
    status,
    openLayout,
    regenerateLayout,
    reset,
    activeDocumentId,
    activeFilename,
  };
}
