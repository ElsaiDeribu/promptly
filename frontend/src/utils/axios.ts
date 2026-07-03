import type { AxiosRequestConfig } from 'axios';

import axios from 'axios';
import { HOST_API } from '@/config-global';

// ----------------------------------------------------------------------

const axiosInstance = axios.create({ baseURL: HOST_API });

axiosInstance.interceptors.response.use(
  (res) => res,
  (error) => Promise.reject((error.response && error.response.data) || 'Something went wrong')
);

export default axiosInstance;

// ----------------------------------------------------------------------

export const fetcher = async (args: string | [string, AxiosRequestConfig]) => {
  const [url, config] = Array.isArray(args) ? args : [args];

  const res = await axiosInstance.get(url, { ...config });

  return res.data;
};

// ----------------------------------------------------------------------

export const endpoints = {
  auth: {
    me: '/api/auth/me',
    login: '/api/auth/login',
    register: '/api/auth/register',
  },
  llm: {
    chat: '/api/llm/chat',
    models: '/api/llm/models',
    ragQueryStream: '/api/llm/rag/query/stream',
    memories: '/api/llm/memories',
    memoryDetail: (id: string) => `/api/llm/memories/${id}`,
    createUploadUrl: '/api/llm/documents/create-upload-url',
    documents: '/api/llm/documents',
    completeUpload: (id: string) => `/api/llm/documents/${id}/complete-upload`,
    documentDetail: (id: string) => `/api/llm/documents/${id}`,
    generateEvalExamples: (id: string) => `/api/llm/documents/${id}/generate-eval-examples`,
    evalExamples: (id: string) => `/api/llm/documents/${id}/eval-examples`,
    documentLayout: (id: string) => `/api/llm/documents/${id}/layout`,
    generateDocumentLayout: (id: string) => `/api/llm/documents/${id}/layout/generate`,
    studyOutline: (id: string) => `/api/llm/documents/${id}/study-outline`,
    generateStudyOutline: (id: string) => `/api/llm/documents/${id}/study-outline/generate`,
    reviseStudyOutline: (id: string) => `/api/llm/documents/${id}/study-outline/revise`,
    studyProgress: (id: string) => `/api/llm/documents/${id}/study-progress`,
    sectionNotes: (docId: string, sectionId: string) =>
      `/api/llm/documents/${docId}/study-sections/${sectionId}/notes`,
    sectionQuestions: (docId: string, sectionId: string) =>
      `/api/llm/documents/${docId}/study-sections/${sectionId}/questions`,
  },
};
