import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import type { ReactNode } from 'react';

export function AppShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  const { authEnabled, authenticated, user, logout } = useAuth();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate('/login');
  }

  return (
    <div className="page-wrap">
      <header className="header">
        <h1>{title}</h1>
        <p className="sub">{subtitle}</p>
        <nav className="top-nav">
          <Link to="/operator">Operator</Link>
          <Link to="/admin">Admin</Link>
        </nav>
        <div className="auth-strip">
          <span>
            {authEnabled
              ? authenticated
                ? `Signed in as ${user?.username || 'user'} (${user?.role || 'operator'})`
                : 'Not signed in'
              : 'Auth disabled (local mode)'}
          </span>
          {authEnabled && authenticated ? (
            <button className="btn btn-secondary" onClick={onLogout}>
              Logout
            </button>
          ) : null}
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
