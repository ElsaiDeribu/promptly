import axios, { endpoints } from '@/utils/axios';
import { useCallback, useState } from 'react';

import { resolveErrorMessage } from '../multimodal-rag/utils';

import type { StudySectionProgress } from './types';

// ----------------------------------------------------------------------

type UseStudyProgressReturn = {
  progress: Record<string, StudySectionProgress>;
  loading: boolean;
  error: string;
  refresh: (documentId: string) => Promise<void>;
  markComplete: (documentId: string, sectionId: string, completed: boolean) => Promise<void>;
  saveNotes: (documentId: string, sectionId: string, notes: string) => Promise<void>;
  completedCount: number;
};

export function useStudyProgress(): UseStudyProgressReturn {
  const [progress, setProgress] = useState<Record<string, StudySectionProgress>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async (documentId: string) => {
    setLoading(true);
    setError('');
    try {
      const { data } = await axios.get<StudySectionProgress[]>(
        endpoints.llm.studyProgress(documentId)
      );
      const map: Record<string, StudySectionProgress> = {};
      for (const item of data) {
        map[item.section_id] = item;
      }
      setProgress(map);
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to load study progress'));
    } finally {
      setLoading(false);
    }
  }, []);

  const updateProgress = useCallback(
    async (
      documentId: string,
      sectionId: string,
      payload: { completed?: boolean; notes?: string }
    ) => {
      const { data } = await axios.put<StudySectionProgress>(
        endpoints.llm.studyProgress(documentId),
        { section_id: sectionId, ...payload }
      );
      setProgress((prev) => ({ ...prev, [sectionId]: data }));
    },
    []
  );

  const markComplete = useCallback(
    async (documentId: string, sectionId: string, completed: boolean) => {
      try {
        await updateProgress(documentId, sectionId, { completed });
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to update progress'));
      }
    },
    [updateProgress]
  );

  const saveNotes = useCallback(
    async (documentId: string, sectionId: string, notes: string) => {
      try {
        await updateProgress(documentId, sectionId, { notes });
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to save notes'));
      }
    },
    [updateProgress]
  );

  const completedCount = Object.values(progress).filter((p) => p.completed).length;

  return {
    progress,
    loading,
    error,
    refresh,
    markComplete,
    saveNotes,
    completedCount,
  };
}
