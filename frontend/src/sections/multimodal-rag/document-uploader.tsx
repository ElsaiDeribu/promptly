import { Loader2 } from 'lucide-react';
import LoadingButton from '@/components/ui/loading-button';

import type { DocumentStatus, TrackedDocument } from './types';

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

function isInProgress(status: DocumentStatus): boolean {
  return status === 'pending' || status === 'uploaded' || status === 'processing';
}

type DocumentUploaderProps = {
  uploading: boolean;
  hasSelectedFile: boolean;
  successMessage: string;
  documents: TrackedDocument[];
  fileInputRef: React.RefObject<HTMLInputElement>;
  onSelectFile: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onBrowse: () => void;
  onUploadAndProcess: () => void;
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
}: DocumentUploaderProps) {
  return (
    <div className="rounded-lg border bg-muted/30 p-2">
      <div className="mb-2 text-sm font-medium">Upload PDF Documents</div>

      <div className="flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={onSelectFile}
          disabled={uploading}
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
        <LoadingButton
          type="button"
          disabled={uploading}
          onClick={onBrowse}
          variant="secondary"
          className="shrink-0"
        >
          Browse
        </LoadingButton>
        <LoadingButton
          type="button"
          loading={uploading}
          disabled={!hasSelectedFile || uploading}
          onClick={onUploadAndProcess}
          className="shrink-0"
        >
          {uploading ? 'Uploading...' : 'Upload and Process'}
        </LoadingButton>
      </div>

      {successMessage && (
        <div className="mt-2 rounded-md border border-green-600/40 bg-green-50 p-2 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
          {successMessage}
        </div>
      )}

      {documents.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Documents:</div>
          <div className="flex flex-wrap gap-1.5">
            {documents.map((doc) => (
              <span
                key={doc.id}
                title={doc.errorMessage || undefined}
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs ${STATUS_CHIP_CLASSES[doc.status]}`}
              >
                {isInProgress(doc.status) && <Loader2 className="h-3 w-3 animate-spin" />}
                <span className="font-medium">{doc.filename}</span>
                <span className="opacity-70">· {STATUS_LABELS[doc.status]}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
