export type OutlineGenerationStatus = 'none' | 'processing' | 'completed' | 'failed';

export type StudySection = {
  id: string;
  title: string;
  level: number;
  parent_id: string | null;
  order: number;
  page_start: number;
  page_end: number;
};

export type StudyOutline = {
  filename: string;
  sections: StudySection[];
};

export type StudyOutlineResponse = {
  document_id: number;
  outline_generation_status: OutlineGenerationStatus;
  outline_error_message?: string;
  outline?: StudyOutline;
};

export type StudySectionProgress = {
  section_id: string;
  completed: boolean;
  completed_at: string | null;
  notes: string;
};

export type StudyQuestion = {
  question: string;
  hint: string;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
};
