import axios, { endpoints } from '@/utils/axios';
import { useRef, useState, useEffect, useCallback } from 'react';

import { resolveErrorMessage } from './utils';

import type {
  TrackedDocument,
  DocumentDetailResponse,
  CompleteUploadResponse,
  CreateUploadUrlResponse,
  EvalExamplesStatusResponse,
  GenerateEvalExamplesResponse,
} from './types';

// ----------------------------------------------------------------------

const DEFAULT_CONTENT_TYPE = 'application/pdf';

// Back off over time — no need to hammer every 30s for an hour
const POLL_INTERVALS_MS = [30_000, 60_000, 120_000];
const MAX_POLL_INTERVAL_MS = 120_000;
const MAX_POLL_DURATION_MS = 60 * 60 * 1000; // ~1 hour before we give up polling
const EVAL_POLL_INTERVAL_MS = 3000;
const EVAL_POLL_TIMEOUT_MS = 20 * 60 * 1000;

function getPollIntervalMs(scheduleIndex: number): number {
  return scheduleIndex < POLL_INTERVALS_MS.length
    ? POLL_INTERVALS_MS[scheduleIndex]
    : MAX_POLL_INTERVAL_MS;
}

type UseDocumentUploadReturn = {
  uploading: boolean;
  error: string;
  successMessage: string;
  documents: TrackedDocument[];
  selectedFile: File | null;
  fileInputRef: React.RefObject<HTMLInputElement>;
  openFilePicker: () => void;
  selectFile: (file: File | null) => void;
  uploadSelectedFile: () => Promise<void>;
  generateEvalExamples: (documentId: string) => Promise<void>;
  resetFeedback: () => void;
};

/**
 * Handles the three-step direct-to-S3 upload flow:
 *   1. Request a pre-signed upload URL from the backend.
 *   2. PUT the file straight to storage (no Django round-trip, no auth header).
 *   3. Notify the backend so async processing can start.
 */
export function useDocumentUpload(): UseDocumentUploadReturn {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [documents, setDocuments] = useState<TrackedDocument[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Outstanding poll timers keyed by document id, so we can cancel on unmount.
  const pollTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(
    () => () => {
      Object.values(pollTimers.current).forEach(clearTimeout);
      pollTimers.current = {};
    },
    []
  );

  const updateDocument = useCallback((id: string, patch: Partial<TrackedDocument>) => {
    setDocuments((prev) => prev.map((doc) => (doc.id === id ? { ...doc, ...patch } : doc)));
  }, []);

  /**
   * Polls the document detail endpoint until the backend reports a terminal
   * status (`processed` or `failed`), or MAX_POLL_DURATION_MS elapses.
   */
  const startPolling = useCallback(
    (documentId: string) => {
      const startedAt = Date.now();
      let scheduleIndex = 0;

      const scheduleNext = () => {
        if (Date.now() - startedAt >= MAX_POLL_DURATION_MS) {
          delete pollTimers.current[documentId];
          return;
        }

        const delay = getPollIntervalMs(scheduleIndex);
        scheduleIndex += 1;
        pollTimers.current[documentId] = setTimeout(tick, delay);
      };

      const tick = async () => {
        try {
          const { data } = await axios.get<DocumentDetailResponse>(
            endpoints.llm.documentDetail(documentId)
          );

          updateDocument(documentId, {
            status: data.status,
            errorMessage: data.error_message || undefined,
            evalGenerationStatus: data.eval_generation_status,
            evalExampleCount: data.eval_example_count,
          });

          if (data.status === 'processed' || data.status === 'failed') {
            delete pollTimers.current[documentId];
            return;
          }
        } catch {
          // Transient error (network blip, etc.) - keep polling until we run
          // out of time rather than failing the whole upload.
        }

        scheduleNext();
      };

      scheduleNext();
    },
    [updateDocument]
  );

  const pollEvalGeneration = useCallback(
    (documentId: string) =>
      new Promise<void>((resolve, reject) => {
        const startedAt = Date.now();

        const tick = async () => {
          if (Date.now() - startedAt >= EVAL_POLL_TIMEOUT_MS) {
            updateDocument(documentId, { generatingEval: false });
            reject(new Error('Timed out waiting for eval example generation'));
            return;
          }

          try {
            const { data } = await axios.get<EvalExamplesStatusResponse>(
              endpoints.llm.evalExamples(documentId)
            );

            updateDocument(documentId, {
              evalGenerationStatus: data.eval_generation_status,
              evalExampleCount: data.eval_example_count,
            });

            if (data.eval_generation_status === 'completed') {
              updateDocument(documentId, { generatingEval: false });
              resolve();
              return;
            }

            if (data.eval_generation_status === 'failed') {
              updateDocument(documentId, { generatingEval: false });
              reject(new Error('Failed to generate eval examples'));
              return;
            }
          } catch (error) {
            updateDocument(documentId, { generatingEval: false });
            reject(error);
            return;
          }

          setTimeout(tick, EVAL_POLL_INTERVAL_MS);
        };

        tick();
      }),
    [updateDocument]
  );

  const generateEvalExamples = useCallback(
    async (documentId: string) => {
      setError('');
      setSuccessMessage('');
      updateDocument(documentId, {
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
    [pollEvalGeneration, updateDocument]
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
      setDocuments((prev) => [
        ...prev,
        { id: documentId, filename: file.name, status: completeData?.status || 'uploaded' },
      ]);

      startPolling(documentId);
      setSelectedFile(null);

      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (e) {
      setError(resolveErrorMessage(e, 'Failed to upload PDF'));
    } finally {
      setUploading(false);
    }
  }, [selectedFile, startPolling]);

  return {
    uploading,
    error,
    successMessage,
    documents,
    selectedFile,
    fileInputRef,
    openFilePicker,
    selectFile,
    uploadSelectedFile,
    generateEvalExamples,
    resetFeedback,
  };
}
