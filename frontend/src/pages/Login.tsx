import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError, setToken } from '../api/client';
import type { AuthResponse } from '../types/api';
import { useAppStore } from '../store/app';
import { cn } from '../utils/format';
import { toast } from '../store/toast';
import { Button, Input } from '../components/controls';
import { Spinner } from '../components/ui';

const DEMO_USERNAME = 'demo';
const DEMO_PASSWORD = 'demo123456';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const token = useAppStore((s) => s.token);
  const setAuth = useAppStore((s) => s.setAuth);

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState(DEMO_USERNAME);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (token) return <Navigate to="/" replace />;

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const submit = async () => {
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const path = mode === 'login' ? '/auth/login' : '/auth/register';
      const res = await api.post<AuthResponse>(path, {
        username: username.trim(),
        password,
        ...(mode === 'register' && email.trim() ? { email: email.trim() } : {}),
      });
      setToken(res.access_token);
      setAuth(res.access_token, res.user);
      toast(mode === 'login' ? '登录成功' : '注册成功', 'success');
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '请求失败，请确认后端服务已启动');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      {/* 背景光晕 */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-96 w-96 rounded-full bg-red-500/10 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-blue-500/10 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-red-500 to-amber-500 text-2xl font-bold text-white shadow-glow">
            基
          </div>
          <h1 className="text-xl font-bold text-zinc-100">基金智能分析预测平台</h1>
          <p className="mt-1 text-xs text-zinc-500">
            量化评分 · 趋势预测 · AI 对话 · 数据透明可追溯
          </p>
        </div>

        <div className="card p-6">
          <div className="mb-5 grid grid-cols-2 rounded-lg border border-white/10 bg-surface-2 p-0.5">
            {(
              [
                { v: 'login', l: '登录' },
                { v: 'register', l: '注册' },
              ] as const
            ).map((m) => (
              <button
                key={m.v}
                onClick={() => {
                  setMode(m.v);
                  setError(null);
                }}
                className={cn(
                  'rounded-md py-2 text-sm font-medium transition',
                  mode === m.v ? 'bg-accent/20 text-accent' : 'text-zinc-400 hover:text-zinc-100',
                )}
              >
                {m.l}
              </button>
            ))}
          </div>

          <div className="space-y-3.5">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">用户名</label>
              <Input value={username} onChange={setUsername} placeholder="请输入用户名" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">密码</label>
              <Input
                type="password"
                value={password}
                onChange={setPassword}
                placeholder="请输入密码"
              />
            </div>
            {mode === 'register' && (
              <div>
                <label className="mb-1 block text-xs text-zinc-500">邮箱（可选）</label>
                <Input value={email} onChange={setEmail} placeholder="you@example.com" />
              </div>
            )}
            {error && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                {error}
              </div>
            )}
            <Button
              variant="primary"
              className="w-full py-2.5"
              onClick={() => void submit()}
              disabled={loading}
            >
              {loading ? <Spinner className="h-4 w-4" /> : mode === 'login' ? '登 录' : '注 册'}
            </Button>
            <p className="text-center text-[11px] text-zinc-600">
              演示账号：{DEMO_USERNAME} / {DEMO_PASSWORD}（已自动填入）
            </p>
          </div>
        </div>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-zinc-600">
          本平台所有预测均为概率估计与评分，不构成投资建议，不承诺任何收益。
        </p>
      </div>
    </div>
  );
}
