export type ChatRole = 'user' | 'assistant';

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  isStreaming?: boolean;
};

export type CreateUploadUrlResponse = {
  document_id: string;
  upload_url: string;
};

export type DocumentStatus = 'pending' | 'uploaded' | 'processing' | 'processed' | 'failed';

export type CompleteUploadResponse = {
  document_id: string;
  status: DocumentStatus;
  message: string;
};

export type DocumentDetailResponse = {
  id: number;
  original_filename: string;
  content_type: string;
  status: DocumentStatus;
  error_message: string;
  created_at: string;
  updated_at: string;
};

export type TrackedDocument = {
  id: string;
  filename: string;
  status: DocumentStatus;
  errorMessage?: string;
};
