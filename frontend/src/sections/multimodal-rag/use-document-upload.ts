import axios, { endpoints } from '@/utils/axios';
import { useRef, useState, useCallback } from 'react';

import { resolveErrorMessage } from './utils';
import { useDocuments } from '../documents/use-documents';
import { useDocumentLayout } from './use-document-layout';

import type { UseDocumentsReturn } from '../documents/use-documents';
import type {
  TrackedDocument,
  CompleteUploadResponse,
  CreateUploadUrlResponse,
  EvalExamplesStatusResponse,
  GenerateEvalExamplesResponse,
} from './types';

// ----------------------------------------------------------------------

const DEFAULT_CONTENT_TYPE = 'application/pdf';
const EVAL_POLL_INTERVAL_MS = 3000;
const EVAL_POLL_TIMEOUT_MS = 20 * 60 * 1000;

type UseDocumentUploadOptions = {
  library?: UseDocumentsReturn;
};

type UseDocumentUploadReturn = {
  uploading: boolean;
  error: string;
  successMessage: string;
  documents: TrackedDocument[];
  selectedFile: File | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  openFilePicker: () => void;
  selectFile: (file: File | null) => void;
  uploadSelectedFile: () => Promise<void>;
  generateEvalExamples: (documentId: string) => Promise<void>;
  updateDocumentLayoutStatus: (documentId: string, status: TrackedDocument['layoutGenerationStatus']) => void;
  resetFeedback: () => void;
  onViewLayout: (documentId: string, filename: string) => Promise<void>;
  viewingLayoutDocumentId: string | null;
  layoutDialogOpen: boolean;
  setLayoutDialogOpen: (open: boolean) => void;
  layout: ReturnType<typeof useDocumentLayout>;
};

export function useDocumentUpload(options: UseDocumentUploadOptions = {}): UseDocumentUploadReturn {
  const ownedLibrary = useDocuments({ autoFetch: !options.library });
  const library = options.library ?? ownedLibrary;

  const layout = useDocumentLayout();
  const [layoutDialogOpen, setLayoutDialogOpen] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const pollEvalGeneration = useCallback(
    (documentId: string) =>
      new Promise<void>((resolve, reject) => {
        const startedAt = Date.now();

        const tick = async () => {
          if (Date.now() - startedAt >= EVAL_POLL_TIMEOUT_MS) {
            library.updateDocument(documentId, { generatingEval: false });
            reject(new Error('Timed out waiting for eval example generation'));
            return;
          }

          try {
            const { data } = await axios.get<EvalExamplesStatusResponse>(
              endpoints.llm.evalExamples(documentId)
            );

            library.updateDocument(documentId, {
              evalGenerationStatus: data.eval_generation_status,
              evalExampleCount: data.eval_example_count,
            });

            if (data.eval_generation_status === 'completed') {
              library.updateDocument(documentId, { generatingEval: false });
              resolve();
              return;
            }

            if (data.eval_generation_status === 'failed') {
              library.updateDocument(documentId, { generatingEval: false });
              reject(new Error('Failed to generate eval examples'));
              return;
            }
          } catch (pollError) {
            library.updateDocument(documentId, { generatingEval: false });
            reject(pollError);
            return;
          }

          setTimeout(tick, EVAL_POLL_INTERVAL_MS);
        };

        tick();
      }),
    [library]
  );

  const generateEvalExamples = useCallback(
    async (documentId: string) => {
      setError('');
      setSuccessMessage('');
      library.updateDocument(documentId, {
        generatingEval: true,
        evalGenerationStatus: 'processing',
      });

      try {
        await axios.post<GenerateEvalExamplesResponse>(
          endpoints.llm.generateEvalExamples(documentId)
        );
        await pollEvalGeneration(documentId);
        setSuccessMessage('Eval examples added to the golden dataset.');
      } catch (e) {
        setError(resolveErrorMessage(e, 'Failed to generate eval examples'));
      }
    },
    [library, pollEvalGeneration]
  );

  const resetFeedback = useCallback(() => {
    setError('');
    setSuccessMessage('');
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const selectFile = useCallback((file: File | null) => {
    setError('');
    setSuccessMessage('');
    setSelectedFile(file);
  }, []);

  const uploadSelectedFile = useCallback(async () => {
    if (!selectedFile) {
      setError('Please select a PDF file first');
      return;
    }

    const file = selectedFile;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF file');
      return;
    }

    setError('');
    setSuccessMessage('');
    setUploading(true);

    const contentType = file.type || DEFAULT_CONTENT_TYPE;

    try {
      const { data } = await axios.post<CreateUploadUrlResponse>(endpoints.llm.createUploadUrl, {
        filename: file.name,
        content_type: contentType,
      });

      const { document_id: documentId, upload_url: uploadUrl } = data;

      const putRes = await fetch(uploadUrl, {
        method: 'PUT',
        headers: { 'Content-Type': contentType },
        body: file,
      });

      if (!putRes.ok) {
        throw new Error(`Upload to storage failed (HTTP ${putRes.status})`);
      }

      const { data: completeData } = await axios.post<CompleteUploadResponse>(
        endpoints.llm.completeUpload(documentId)
      );

      setSuccessMessage(`Uploaded: ${file.name}. Track its status below.`);
      library.addDocument({
        id: documentId,
        filename: file.name,
        status: completeData?.status || 'uploaded',
      });

      library.startPolling(documentId);
      setSelectedFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to upload PDF'));
    } finally {
      setUploading(false);
    }
  }, [library, selectedFile]);

  const updateDocumentLayoutStatus = useCallback(
    (documentId: string, layoutGenerationStatus: TrackedDocument['layoutGenerationStatus']) => {
      library.updateDocument(documentId, { layoutGenerationStatus });
    },
    [library]
  );

  const onViewLayout = useCallback(
    async (documentId: string, filename: string) => {
      setError('');
      setLayoutDialogOpen(true);
      const result = await layout.openLayout(documentId, filename);
      if (result === 'completed') {
        updateDocumentLayoutStatus(documentId, 'completed');
      } else if (result === 'failed') {
        updateDocumentLayoutStatus(documentId, 'failed');
      }
    },
    [layout, updateDocumentLayoutStatus]
  );

  return {
    uploading,
    error,
    successMessage,
    documents: library.documents,
    selectedFile,
    fileInputRef,
    openFilePicker,
    selectFile,
    uploadSelectedFile,
    generateEvalExamples,
    updateDocumentLayoutStatus,
    resetFeedback,
    onViewLayout,
    viewingLayoutDocumentId: layout.loading ? layout.activeDocumentId : null,
    layoutDialogOpen,
    setLayoutDialogOpen,
    layout,
  };
}
