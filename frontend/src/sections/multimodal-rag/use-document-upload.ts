import axios, { endpoints } from '@/utils/axios';
import { useRef, useState, useEffect, useCallback } from 'react';

import { resolveErrorMessage } from './utils';

import type {
  TrackedDocument,
  DocumentDetailResponse,
  CompleteUploadResponse,
  CreateUploadUrlResponse,
} from './types';

// ----------------------------------------------------------------------

const DEFAULT_CONTENT_TYPE = 'application/pdf';

// How often to ask the backend for the processing status, and for how long.
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 90; // ~3 minutes before we give up polling

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
   * status (`processed` or `failed`), or we exhaust MAX_POLL_ATTEMPTS.
   */
  const startPolling = useCallback(
    (documentId: string) => {
      let attempts = 0;

      const tick = async () => {
        attempts += 1;

        try {
          const { data } = await axios.get<DocumentDetailResponse>(
            endpoints.llm.documentDetail(documentId)
          );

          updateDocument(documentId, {
            status: data.status,
            errorMessage: data.error_message || undefined,
          });

          if (data.status === 'processed' || data.status === 'failed') {
            delete pollTimers.current[documentId];
            return;
          }
        } catch {
          // Transient error (network blip, etc.) - keep polling until we run
          // out of attempts rather than failing the whole upload.
        }

        if (attempts >= MAX_POLL_ATTEMPTS) {
          delete pollTimers.current[documentId];
          return;
        }

        pollTimers.current[documentId] = setTimeout(tick, POLL_INTERVAL_MS);
      };

      pollTimers.current[documentId] = setTimeout(tick, POLL_INTERVAL_MS);
    },
    [updateDocument]
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
    resetFeedback,
  };
}
