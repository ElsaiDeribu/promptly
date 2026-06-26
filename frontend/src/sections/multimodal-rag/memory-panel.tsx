import { Brain, Loader2, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

import type { UserMemory } from './types';

// ----------------------------------------------------------------------

type MemoryPanelProps = {
  className?: string;
  memories: UserMemory[];
  loading: boolean;
  onDelete: (memoryId: string) => void;
  onRefresh: () => void;
};

export default function MemoryPanel({
  className,
  memories,
  loading,
  onDelete,
  onRefresh,
}: MemoryPanelProps) {
  return (
    <div className={cn('flex flex-col rounded-lg border bg-muted/30 p-3', className)}>
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Brain className="h-4 w-4" />
          Saved Memories
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
          Refresh
        </Button>
      </div>

      <p className="mb-3 shrink-0 text-xs text-muted-foreground">
        The assistant saves preferences and facts you share across chat sessions.
      </p>

      {loading && memories.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading memories...
        </div>
      ) : null}

      {!loading && memories.length === 0 ? (
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          No memories yet. Tell the assistant something about yourself and it may remember it
          in future chats.
        </div>
      ) : null}

      {memories.length > 0 ? (
        <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto">
          {memories.map((memory) => (
            <li
              key={memory.memory_id}
              className="flex items-start justify-between gap-3 rounded-md border bg-background p-3"
            >
              <div className="min-w-0">
                <p className="text-sm">{memory.content}</p>
                {memory.context ? (
                  <p className="mt-1 text-xs text-muted-foreground">{memory.context}</p>
                ) : null}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => onDelete(memory.memory_id)}
                aria-label="Delete memory"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
