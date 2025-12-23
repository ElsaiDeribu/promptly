import { useAuthContext } from '@/auth/hooks';

// ----------------------------------------------------------------------

type RoleBasedGuardProp = {
  hasContent?: boolean;
  roles?: string[];
  children: React.ReactNode;
};

export default function RoleBasedGuard({ hasContent, roles, children }: RoleBasedGuardProp) {
  // Logic here to get current user role
  const { user } = useAuthContext();

  // const currentRole = 'user';
  const currentRole = user?.role; // admin;

  if (typeof roles !== 'undefined' && !roles.includes(currentRole)) {
    return hasContent ? (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div>
          <p style={{ marginBottom: 2 }}>Permission Denied</p>
        </div>

        <div>
          <p style={{ color: 'text.secondary' }}>You do not have permission to access this page</p>
        </div>

        <div>
          <p style={{ marginBottom: 2 }}>Permission Denied, forbidden illustration</p>
        </div>
      </div>
    ) : null;
  }

  return <> {children} </>;
}
