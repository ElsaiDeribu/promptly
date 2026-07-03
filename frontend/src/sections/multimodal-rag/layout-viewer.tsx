import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import LoadingButton from '@/components/ui/loading-button';
import { Loader2 } from 'lucide-react';
import { useMemo } from 'react';

import { labelClass, LayoutPageView } from './layout-page-view';

import type { DocumentLayout } from './types';

type LayoutViewerDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filename: string | null;
  layout: DocumentLayout | null;
  loading: boolean;
  error: string;
  onRegenerate: () => void;
};

export default function LayoutViewerDialog({
  open,
  onOpenChange,
  filename,
  layout,
  loading,
  error,
  onRegenerate,
}: LayoutViewerDialogProps) {
  const legendLabels = useMemo(() => {
    if (!layout) return [];
    const labels = new Set<string>();
    layout.pages.forEach((page) => page.elements.forEach((element) => labels.add(element.label)));
    return Array.from(labels).sort();
  }, [layout]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] w-[min(96vw,72rem)] max-w-none flex-col gap-4 overflow-hidden sm:max-w-none">
        <DialogHeader className="shrink-0">
          <DialogTitle>Document Layout</DialogTitle>
          <DialogDescription>
            {filename ? (
              <>
                Docling layout for <span className="font-medium text-foreground">{filename}</span>.
                Hover boxes to inspect detected elements.
              </>
            ) : (
              'Docling layout extraction with bounding boxes per page.'
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
          {loading ? (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Extracting layout with Docling…
            </div>
          ) : null}

          {error ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          {!loading && layout ? (
            <>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-muted-foreground">
                  {layout.page_count} page{layout.page_count === 1 ? '' : 's'}
                </span>
                {legendLabels.map((label) => (
                  <span
                    key={label}
                    className={`rounded border px-2 py-0.5 capitalize ${labelClass(label)}`}
                  >
                    {label.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>

              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
                {layout.pages.map((page) => (
                  <LayoutPageView key={page.page_no} page={page} />
                ))}
              </div>
            </>
          ) : null}

          <div className="flex shrink-0 justify-end gap-2 border-t pt-3">
            <LoadingButton
              type="button"
              variant="outline"
              loading={loading}
              disabled={loading}
              onClick={onRegenerate}
            >
              Regenerate layout
            </LoadingButton>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
