import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, RefreshCw, Trash2 } from 'lucide-react';
import LoadingButton from '@/components/ui/loading-button';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogTitle,
  AlertDialogCancel,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogDescription,
} from '@/components/ui/alert-dialog';
import {
  Card,
  CardTitle,
  CardHeader,
  CardContent,
  CardDescription,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

import LayoutViewerDialog from '../multimodal-rag/layout-viewer';
import { useDocumentLayout } from '../multimodal-rag/use-document-layout';
import { StudyCompanionView } from '../study-companion';
import { formatDocumentDate } from './document-utils';
import { useDocuments } from './use-documents';

import type { DocumentStatus, TrackedDocument } from '../multimodal-rag/types';

// ----------------------------------------------------------------------

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: 'Pending upload',
  uploaded: 'Queued',
  processing: 'Processing',
  processed: 'Ready',
  failed: 'Failed',
};

const STATUS_CLASSES: Record<DocumentStatus, string> = {
  pending: 'text-muted-foreground',
  uploaded: 'text-amber-600 dark:text-amber-400',
  processing: 'text-amber-600 dark:text-amber-400',
  processed: 'text-green-700 dark:text-green-400',
  failed: 'text-destructive',
};

function DocumentRow({
  doc,
  selected,
  deleting,
  viewingLayout,
  onSelect,
  onViewLayout,
  onDelete,
}: {
  doc: TrackedDocument;
  selected: boolean;
  deleting: boolean;
  viewingLayout: boolean;
  onSelect: () => void;
  onViewLayout: () => void;
  onDelete: () => void;
}) {
  const canStudy = doc.status === 'processed';
  const canViewLayout = doc.status !== 'pending' && doc.status !== 'failed';

  return (
    <div
      className={cn(
        'flex flex-col gap-2 rounded-lg border p-3 transition-colors',
        selected && 'border-primary bg-primary/5',
        canStudy && 'cursor-pointer hover:bg-muted/50',
        !canStudy && 'opacity-80'
      )}
      onClick={canStudy ? onSelect : undefined}
      onKeyDown={
        canStudy
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
      role={canStudy ? 'button' : undefined}
      tabIndex={canStudy ? 0 : undefined}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{doc.filename}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span className={STATUS_CLASSES[doc.status]}>{STATUS_LABELS[doc.status]}</span>
          <span>{formatDocumentDate(doc.createdAt)}</span>
        </div>
        {doc.errorMessage ? (
          <div className="mt-1 text-xs text-destructive">{doc.errorMessage}</div>
        ) : null}
      </div>

      <div className="flex shrink-0 justify-end gap-1">
        {canViewLayout ? (
          <LoadingButton
            type="button"
            size="sm"
            variant="outline"
            loading={viewingLayout}
            disabled={viewingLayout}
            onClick={(e) => {
              e.stopPropagation();
              onViewLayout();
            }}
            className="h-8 px-2 text-xs"
          >
            {doc.layoutGenerationStatus === 'completed' ? 'Layout' : 'Get layout'}
          </LoadingButton>
        ) : null}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={deleting}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="h-8 w-8 text-destructive hover:text-destructive"
        >
          {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}

export default function DocumentsView() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedDocumentId = searchParams.get('documentId') ?? '';

  const library = useDocuments();
  const layout = useDocumentLayout();

  const [layoutDialogOpen, setLayoutDialogOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; filename: string } | null>(
    null
  );

  function selectDocument(documentId: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (documentId) {
          next.set('documentId', documentId);
        } else {
          next.delete('documentId');
        }
        return next;
      },
      { replace: true }
    );
  }

  function requestDelete(documentId: string, filename: string) {
    setDeleteTarget({ id: documentId, filename });
  }

  const viewingLayoutDocumentId = layout.loading ? layout.activeDocumentId : null;

  async function handleViewLayout(documentId: string, filename: string) {
    setLayoutDialogOpen(true);
    const result = await layout.openLayout(documentId, filename);
    if (result === 'completed') {
      library.updateDocument(documentId, { layoutGenerationStatus: 'completed' });
    } else if (result === 'failed') {
      library.updateDocument(documentId, { layoutGenerationStatus: 'failed' });
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setDeleteTarget(null);
    setDeletingId(id);
    try {
      await library.deleteDocument(id);
      if (selectedDocumentId === id) {
        selectDocument(null);
      }
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <div className="mx-auto flex h-[calc(100dvh-5rem)] w-full gap-1">
        <Card className="flex w-[20%] shrink-0 flex-col">
          <CardHeader className="shrink-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <CardTitle className="text-base">Documents</CardTitle>
                <CardDescription className="text-xs">
                  Select a document to study
                </CardDescription>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={library.loading}
                onClick={() => library.refreshDocuments()}
                className="h-8 w-8 shrink-0"
              >
                <RefreshCw className={`h-4 w-4 ${library.loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col gap-2 pb-4">
            {library.error ? (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {library.error}
              </div>
            ) : null}

            {library.loading && library.documents.length === 0 ? (
              <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : null}

            {!library.loading && library.documents.length === 0 ? (
              <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                No documents yet.
              </div>
            ) : null}

            {library.documents.length > 0 ? (
              <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
                {library.documents.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    selected={selectedDocumentId === doc.id}
                    deleting={deletingId === doc.id}
                    viewingLayout={viewingLayoutDocumentId === doc.id}
                    onSelect={() => selectDocument(doc.id)}
                    onViewLayout={() => handleViewLayout(doc.id, doc.filename)}
                    onDelete={() => requestDelete(doc.id, doc.filename)}
                  />
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="min-h-0 min-w-0 flex-1">
          {selectedDocumentId ? (
            <StudyCompanionView
              documentId={selectedDocumentId}
              embedded
              onDeselect={() => selectDocument(null)}
            />
          ) : (
            <Card className="flex h-full items-center justify-center">
              <CardContent className="py-12 text-center text-sm text-muted-foreground">
                Select a processed document from the list to start studying.
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <LayoutViewerDialog
        open={layoutDialogOpen}
        onOpenChange={(open) => {
          setLayoutDialogOpen(open);
          if (!open) layout.reset();
        }}
        filename={layout.activeFilename}
        layout={layout.layout}
        loading={layout.loading}
        error={layout.error}
        onRegenerate={layout.regenerateLayout}
      />

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget
                ? `"${deleteTarget.filename}" will be permanently deleted. This cannot be undone.`
                : 'This document will be permanently deleted. This cannot be undone.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button variant="destructive" onClick={confirmDelete} disabled={!deleteTarget}>
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
