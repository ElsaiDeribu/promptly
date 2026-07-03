import axios, { endpoints } from '@/utils/axios';
import { useCallback, useState } from 'react';

import { resolveErrorMessage } from '../multimodal-rag/utils';

import type { StudyOutline, StudyOutlineResponse } from './types';

// ----------------------------------------------------------------------

const OUTLINE_POLL_INTERVAL_MS = 3000;
const OUTLINE_POLL_TIMEOUT_MS = 15 * 60 * 1000;

type UseStudyOutlineReturn = {
  outline: StudyOutline | null;
  loading: boolean;
  revising: boolean;
  error: string;
  status: StudyOutlineResponse['outline_generation_status'] | null;
  generateOutline: (documentId: string, force?: boolean) => Promise<'completed' | 'failed' | null>;
  reviseOutline: (documentId: string, instruction: string) => Promise<'completed' | 'failed' | null>;
  reset: () => void;
};

export function useStudyOutline(): UseStudyOutlineReturn {
  const [outline, setOutline] = useState<StudyOutline | null>(null);
  const [loading, setLoading] = useState(false);
  const [revising, setRevising] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<StudyOutlineResponse['outline_generation_status'] | null>(
    null
  );

  const pollOutline = useCallback(async (documentId: string) => {
    const startedAt = Date.now();

    while (Date.now() - startedAt < OUTLINE_POLL_TIMEOUT_MS) {
      const { data } = await axios.get<StudyOutlineResponse>(
        endpoints.llm.studyOutline(documentId)
      );

      setStatus(data.outline_generation_status);

      if (data.outline_generation_status === 'completed' && data.outline) {
        setOutline(data.outline);
        return;
      }

      if (data.outline_generation_status === 'failed') {
        throw new Error(data.outline_error_message || 'Study outline generation failed');
      }

      await new Promise((resolve) => setTimeout(resolve, OUTLINE_POLL_INTERVAL_MS));
    }

    throw new Error('Timed out waiting for study outline');
  }, []);

  const generateOutline = useCallback(
    async (documentId: string, force = false): Promise<'completed' | 'failed' | null> => {
      setLoading(true);
      setError('');
      setOutline(null);

      try {
        const { data, status: httpStatus } = await axios.post<StudyOutlineResponse>(
          endpoints.llm.generateStudyOutline(documentId),
          { force }
        );

        setStatus(data.outline_generation_status);

        if (data.outline) {
          setOutline(data.outline);
          return 'completed';
        }

        if (httpStatus === 202 || data.outline_generation_status === 'processing') {
          await pollOutline(documentId);
          return 'completed';
        }

        if (data.outline_generation_status === 'failed') {
          throw new Error(data.outline_error_message || 'Study outline generation failed');
        }

        return null;
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to generate study outline'));
        return 'failed';
      } finally {
        setLoading(false);
      }
    },
    [pollOutline]
  );

  const reviseOutline = useCallback(
    async (documentId: string, instruction: string): Promise<'completed' | 'failed' | null> => {
      setRevising(true);
      setError('');

      try {
        const { status: httpStatus } = await axios.post(
          endpoints.llm.reviseStudyOutline(documentId),
          { instruction }
        );

        if (httpStatus === 202) {
          await pollOutline(documentId);
          return 'completed';
        }

        return null;
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to revise study outline'));
        return 'failed';
      } finally {
        setRevising(false);
      }
    },
    [pollOutline]
  );

  const reset = useCallback(() => {
    setOutline(null);
    setLoading(false);
    setRevising(false);
    setError('');
    setStatus(null);
  }, []);

  return {
    outline,
    loading,
    revising,
    error,
    status,
    generateOutline,
    reviseOutline,
    reset,
  };
}
