// ----------------------------------------------------------------------

const ROOTS = {
  AUTH: '',
  DASHBOARD: '/dashboard',
};

// ----------------------------------------------------------------------

export const paths = {
  page403: '/403',
  page404: '/404',
  page500: '/500',

  dashboard: {
    root: ROOTS.DASHBOARD,
    llmChat: `${ROOTS.DASHBOARD}/llm-chat`,
    multimodalRag: `${ROOTS.DASHBOARD}/multimodal-rag`,
  },

  // AUTH
  auth: {
    login: `${ROOTS.AUTH}/login`,
    register: `${ROOTS.AUTH}/register`,
    forgotPassword: `${ROOTS.AUTH}/forgot-password`,
  },
};
