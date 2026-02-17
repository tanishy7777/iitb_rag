import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import type { Role } from '../lib/api';

export function RequireRole({ roles, children }: { roles: Role[]; children: JSX.Element }) {
  const { loading, authEnabled, authenticated, user } = useAuth();
  const location = useLocation();

  if (loading) return <div className="screen-message">Loading session...</div>;

  if (!authEnabled) {
    return children;
  }

  if (!authenticated || !user) {
    const next = encodeURIComponent(location.pathname || '/operator');
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (!roles.includes(user.role)) {
    return <Navigate to="/operator" replace />;
  }

  return children;
}
