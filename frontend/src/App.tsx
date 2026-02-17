import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/AuthProvider';
import { RequireRole } from './components/RequireRole';
import { LoginPage } from './pages/LoginPage';
import { OperatorPage } from './pages/OperatorPage';
import { AdminPage } from './pages/AdminPage';

function RootRedirect() {
  const { loading, authEnabled, authenticated, user } = useAuth();

  if (loading) {
    return <div className="screen-message">Loading session...</div>;
  }

  if (!authEnabled) {
    return <Navigate to="/operator" replace />;
  }

  if (!authenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={user.role === 'admin' ? '/admin' : '/operator'} replace />;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/operator"
          element={
            <RequireRole roles={['operator', 'admin']}>
              <OperatorPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireRole roles={['admin']}>
              <AdminPage />
            </RequireRole>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
