import { useEffect } from 'react';
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import Layout from './components/Layout';
import { onUnauthorized } from './api/client';
import { useAppStore } from './store/app';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Funds from './pages/Funds';
import FundDetail from './pages/FundDetail';
import Market from './pages/Market';
import News from './pages/News';
import Policy from './pages/Policy';
import Analysis from './pages/Analysis';
import Chat from './pages/Chat';
import Reports from './pages/Reports';
import Settings from './pages/Settings';

function RequireAuth({ children }: { children: React.ReactElement }) {
  const token = useAppStore((s) => s.token);
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

/** 401 全局处理：清除凭证并跳转登录 */
function AuthHandler() {
  const navigate = useNavigate();
  const logout = useAppStore((s) => s.logout);
  useEffect(() => {
    return onUnauthorized(() => {
      logout();
      navigate('/login', { replace: true });
    });
  }, [navigate, logout]);
  return null;
}

export default function App() {
  return (
    <HashRouter>
      <AuthHandler />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/funds" element={<Funds />} />
          <Route path="/funds/:code" element={<FundDetail />} />
          <Route path="/market" element={<Market />} />
          <Route path="/news" element={<News />} />
          <Route path="/policy" element={<Policy />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
