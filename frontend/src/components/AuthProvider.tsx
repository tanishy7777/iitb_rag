import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { fetchAuthMe, logout as logoutApi, type AuthUser } from '../lib/api';

type AuthContextValue = {
  loading: boolean;
  authEnabled: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAuthMe();
      setAuthEnabled(Boolean(data.auth_enabled));
      setAuthenticated(Boolean(data.authenticated));
      setUser(data.authenticated ? data.user || null : null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await logoutApi();
    setAuthenticated(false);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ loading, authEnabled, authenticated, user, refresh, logout }),
    [loading, authEnabled, authenticated, user, refresh, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return value;
}
