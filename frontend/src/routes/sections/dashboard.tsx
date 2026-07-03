import { lazy, Suspense } from 'react';
import { AuthGuard } from '@/auth/guard';
import { Outlet } from 'react-router-dom';
import { LoadingScreen } from '@/components/loading-screen';

// ----------------------------------------------------------------------

const DashboardPage = lazy(() => import('@/pages/dashboard/dashboard'));
const LLMChatPage = lazy(() => import('@/pages/dashboard/llm-chat'));
const MultimodalRagPage = lazy(() => import('@/pages/dashboard/multimodal-rag'));
const DocumentsPage = lazy(() => import('@/pages/dashboard/documents'));
const StudyCompanionPage = lazy(() => import('@/pages/dashboard/study-companion'));

// ----------------------------------------------------------------------

export const dashboardRoutes = [
  {
    path: 'dashboard',
    element: (
      <AuthGuard>
        <Suspense fallback={<LoadingScreen />}>
          <Outlet />
        </Suspense>
      </AuthGuard>
    ),
    children: [
      { element: <DashboardPage />, index: true },
      { path: 'llm-chat', element: <LLMChatPage /> },
      { path: 'multimodal-rag', element: <MultimodalRagPage /> },
      { path: 'documents', element: <DocumentsPage /> },
      { path: 'study/:documentId', element: <StudyCompanionPage /> },
    ],
  },
];
