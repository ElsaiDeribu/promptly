import { lazy, Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { GuestGuard } from '@/auth/guard';
import { SplashScreen } from '@/components/loading-screen';
import AuthLayoutMain from '@/layouts/auth/auth-layout-main';
// ----------------------------------------------------------------------

const LoginPage = lazy(() => import('@/pages/auth/login'));
const RegisterPage = lazy(() => import('@/pages/auth/register'));

// ----------------------------------------------------------------------

const auth = {
  path: '',
  element: (
    <Suspense fallback={<SplashScreen />}>
      <Outlet />
    </Suspense>
  ),
  children: [
    {
      path: 'login',
      element: (
        <GuestGuard>
          <AuthLayoutMain>
            <LoginPage />
          </AuthLayoutMain>
        </GuestGuard>
      ),
    },
    {
      path: 'register',
      element: (
        <GuestGuard>
          <AuthLayoutMain>
            <RegisterPage />
          </AuthLayoutMain>
        </GuestGuard>
      ),
    },
  ],
};

export const authRoutes = [
  {
    path: '',
    children: [auth],
  },
];
