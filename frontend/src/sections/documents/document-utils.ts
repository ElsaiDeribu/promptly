import type { DocumentDetailResponse, TrackedDocument } from '../multimodal-rag/types';

export function mapDocumentFromApi(data: DocumentDetailResponse): TrackedDocument {
  return {
    id: String(data.id),
    filename: data.original_filename,
    status: data.status,
    errorMessage: data.error_message || undefined,
    evalGenerationStatus: data.eval_generation_status,
    evalExampleCount: data.eval_example_count,
    layoutGenerationStatus: data.layout_generation_status,
    outlineGenerationStatus: data.outline_generation_status,
    createdAt: data.created_at,
  };
}

export function formatDocumentDate(iso: string | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}
