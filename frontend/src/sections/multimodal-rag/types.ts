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

export type LayoutGenerationStatus = 'none' | 'processing' | 'completed' | 'failed';

export type OutlineGenerationStatus = 'none' | 'processing' | 'completed' | 'failed';

export type DocumentDetailResponse = {
  id: number;
  original_filename: string;
  content_type: string;
  status: DocumentStatus;
  error_message: string;
  eval_generation_status: EvalGenerationStatus;
  eval_example_count: number;
  layout_generation_status: LayoutGenerationStatus;
  outline_generation_status: OutlineGenerationStatus;
  created_at: string;
  updated_at: string;
};

export type EvalGenerationStatus = 'none' | 'processing' | 'completed' | 'failed';

export type GenerateEvalExamplesResponse = {
  document_id: string;
  eval_generation_status: EvalGenerationStatus;
  message: string;
};

export type EvalExamplesStatusResponse = {
  document_id: number;
  eval_generation_status: EvalGenerationStatus;
  eval_example_count: number;
};

export type TrackedDocument = {
  id: string;
  filename: string;
  status: DocumentStatus;
  errorMessage?: string;
  evalGenerationStatus?: EvalGenerationStatus;
  evalExampleCount?: number;
  generatingEval?: boolean;
  layoutGenerationStatus?: LayoutGenerationStatus;
  generatingLayout?: boolean;
  outlineGenerationStatus?: OutlineGenerationStatus;
  createdAt?: string;
};

export type LayoutBBox = {
  l: number;
  t: number;
  r: number;
  b: number;
};

export type LayoutElement = {
  id: string;
  label: string;
  text: string;
  bbox: LayoutBBox;
};

export type LayoutPage = {
  page_no: number;
  width: number;
  height: number;
  elements: LayoutElement[];
  image_base64?: string | null;
};

/** Layout payload returned by the backend. */
export type DocumentLayout = {
  filename: string;
  page_count: number;
  pages: LayoutPage[];
};

export type DocumentLayoutResponse = {
  document_id: number;
  layout_generation_status: LayoutGenerationStatus;
  layout_error_message?: string;
  layout?: DocumentLayout;
};

export type GenerateDocumentLayoutResponse = {
  document_id: string;
  layout_generation_status: LayoutGenerationStatus;
  message?: string;
  layout?: DocumentLayout;
};

export type UserMemory = {
  memory_id: string;
  content: string;
  context: string;
};
