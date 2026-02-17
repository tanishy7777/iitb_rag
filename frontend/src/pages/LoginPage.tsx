import { FormEvent, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { login } from '../lib/api';
import { useAuth } from '../components/AuthProvider';

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { loading, authEnabled, authenticated, user, refresh } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (loading) return;
    if (!authEnabled) {
      navigate('/operator', { replace: true });
      return;
    }
    if (authenticated) {
      navigate(user?.role === 'admin' ? '/admin' : '/operator', { replace: true });
    }
  }, [loading, authEnabled, authenticated, user, navigate]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError('Username and password are required.');
      return;
    }

    setBusy(true);
    setError('');
    try {
      const data = await login(username.trim(), password);
      await refresh();
      const next = params.get('next');
      if (next && next.startsWith('/')) {
        navigate(next, { replace: true });
        return;
      }
      navigate(data.user?.role === 'admin' ? '/admin' : '/operator', { replace: true });
    } catch (err) {
      const msg = typeof err === 'object' && err && 'message' in err ? String((err as { message?: unknown }).message) : 'Login failed';
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="auth-card">
        <h1>Digital Brain</h1>
        <p className="sub">Sign in with your operator/admin account.</p>
        <form onSubmit={onSubmit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <button className="btn" type="submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Sign In'}
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </form>
      </section>
    </div>
  );
}
