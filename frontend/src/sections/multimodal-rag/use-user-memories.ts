import axios from '@/utils/axios';
import { endpoints } from '@/utils/axios';
import { useCallback, useEffect, useState } from 'react';

import { resolveErrorMessage } from './utils';

import type { UserMemory } from './types';

// ----------------------------------------------------------------------

type UseUserMemoriesReturn = {
  memories: UserMemory[];
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  deleteMemory: (memoryId: string) => Promise<void>;
};

export function useUserMemories(): UseUserMemoriesReturn {
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const { data } = await axios.get<UserMemory[]>(endpoints.llm.memories);
      setMemories(data);
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to load memories'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const deleteMemory = useCallback(
    async (memoryId: string) => {
      setError('');
      try {
        await axios.delete(endpoints.llm.memoryDetail(memoryId));
        setMemories((prev) => prev.filter((memory) => memory.memory_id !== memoryId));
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to delete memory'));
      }
    },
    []
  );

  return { memories, loading, error, refresh, deleteMemory };
}
