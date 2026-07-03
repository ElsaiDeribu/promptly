import { Loader2 } from 'lucide-react';
import LoadingButton from '@/components/ui/loading-button';

import type { DocumentStatus, TrackedDocument, EvalGenerationStatus } from './types';

// ----------------------------------------------------------------------

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: 'Pending',
  uploaded: 'Queued',
  processing: 'Processing',
  processed: 'Ready',
  failed: 'Failed',
};

const STATUS_CHIP_CLASSES: Record<DocumentStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  uploaded: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  processing: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  processed: 'bg-green-600/10 text-green-700 dark:text-green-400',
  failed: 'bg-destructive/10 text-destructive',
};

const EVAL_STATUS_LABELS: Record<EvalGenerationStatus, string> = {
  none: 'No eval set',
  processing: 'Generating eval...',
  completed: 'Eval ready',
  failed: 'Eval failed',
};

function isInProgress(status: DocumentStatus): boolean {
  return status === 'pending' || status === 'uploaded' || status === 'processing';
}

type DocumentUploaderProps = {
  uploading: boolean;
  hasSelectedFile: boolean;
  successMessage: string;
  documents: TrackedDocument[];
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onSelectFile: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onBrowse: () => void;
  onUploadAndProcess: () => void;
  onGenerateEvalExamples: (documentId: string) => void;
  onViewLayout: (documentId: string, filename: string) => void;
  onStudy?: (documentId: string) => void;
  viewingLayoutDocumentId?: string | null;
  /** Hide inline document list (used when a separate list is shown). */
  compactList?: boolean;
};

export default function DocumentUploader({
  uploading,
  hasSelectedFile,
  successMessage,
  documents,
  fileInputRef,
  onSelectFile,
  onBrowse,
  onUploadAndProcess,
  onGenerateEvalExamples,
  onViewLayout,
  onStudy,
  viewingLayoutDocumentId,
  compactList = false,
}: DocumentUploaderProps) {
  return (
    <div className="rounded-lg border bg-muted/30 p-2">
      <div className="mb-2 text-sm font-medium">Upload PDF Documents</div>

      <div className="flex flex-col gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={onSelectFile}
          disabled={uploading}
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
        <div className="flex gap-2">
          <LoadingButton
            type="button"
            disabled={uploading}
            onClick={onBrowse}
            variant="secondary"
            className="flex-1"
          >
            Browse
          </LoadingButton>
          <LoadingButton
            type="button"
            loading={uploading}
            disabled={!hasSelectedFile || uploading}
            onClick={onUploadAndProcess}
            className="flex-1"
          >
            {uploading ? 'Uploading...' : 'Upload and Process'}
          </LoadingButton>
        </div>
      </div>

      {successMessage && (
        <div className="mt-2 rounded-md border border-green-600/40 bg-green-50 p-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
          {successMessage}
        </div>
      )}

      {documents.length > 0 && !compactList && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Documents:</div>
          <div className="flex flex-col gap-1.5">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className={`rounded-md px-2 py-1.5 text-xs ${STATUS_CHIP_CLASSES[doc.status]}`}
              >
                <div className="flex items-start gap-1.5">
                  {isInProgress(doc.status) && <Loader2 className="mt-0.5 h-3 w-3 animate-spin" />}
                  <div className="min-w-0 flex-1">
                    <div className="font-medium break-all">{doc.filename}</div>
                    <div className="opacity-70">
                      {STATUS_LABELS[doc.status]}
                      {doc.evalExampleCount ? ` · ${doc.evalExampleCount} eval examples` : ''}
                    </div>
                    {doc.evalGenerationStatus && doc.evalGenerationStatus !== 'none' ? (
                      <div className="mt-0.5 opacity-70">
                        {EVAL_STATUS_LABELS[doc.evalGenerationStatus]}
                      </div>
                    ) : null}
                    {doc.errorMessage ? (
                      <div className="mt-0.5 text-destructive">{doc.errorMessage}</div>
                    ) : null}
                  </div>
                </div>

                {doc.status !== 'pending' && doc.status !== 'failed' ? (
                  <div className="mt-2 flex flex-col gap-1.5">
                    <LoadingButton
                      type="button"
                      size="sm"
                      variant="outline"
                      loading={viewingLayoutDocumentId === doc.id}
                      disabled={Boolean(viewingLayoutDocumentId) || uploading}
                      onClick={() => onViewLayout(doc.id, doc.filename)}
                      className="h-7 w-full text-xs"
                    >
                      {doc.layoutGenerationStatus === 'completed' ? 'View layout' : 'Get layout'}
                    </LoadingButton>
                    {doc.status === 'processed' ? (
                      <>
                        {onStudy ? (
                          <LoadingButton
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={uploading}
                            onClick={() => onStudy(doc.id)}
                            className="h-7 w-full text-xs"
                          >
                            Study
                          </LoadingButton>
                        ) : null}
                        <LoadingButton
                        type="button"
                        size="sm"
                        variant="outline"
                        loading={doc.generatingEval}
                        disabled={doc.generatingEval || uploading}
                        onClick={() => onGenerateEvalExamples(doc.id)}
                        className="h-7 w-full text-xs"
                      >
                        {doc.evalExampleCount
                          ? 'Regenerate eval examples'
                          : 'Generate eval examples'}
                      </LoadingButton>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
