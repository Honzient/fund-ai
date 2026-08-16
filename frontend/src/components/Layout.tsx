import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/app';
import { api } from '../api/client';
import type { NotificationItem } from '../types/api';
import { cn, timeAgo } from '../utils/format';
import {
  IconBell,
  IconDashboard,
  IconFund,
  IconMarket,
  IconNews,
  IconPolicy,
  IconAnalysis,
  IconChat,
  IconReport,
  IconSettings,
  IconLogout,
  IconUser,
} from './icons';
import ToastHost from './ToastHost';

const NAV_ITEMS = [
  { to: '/', label: '仪表盘', icon: IconDashboard, end: true },
  { to: '/funds', label: '基金', icon: IconFund },
  { to: '/market', label: '市场', icon: IconMarket },
  { to: '/news', label: '新闻', icon: IconNews },
  { to: '/policy', label: '政策', icon: IconPolicy },
  { to: '/analysis', label: '多基金分析', icon: IconAnalysis },
  { to: '/chat', label: 'AI 对话', icon: IconChat },
  { to: '/reports', label: '定时报告', icon: IconReport },
  { to: '/settings', label: '设置', icon: IconSettings },
];

const TITLES: [string, string][] = [
  ['/', '仪表盘'],
  ['/funds', '基金'],
  ['/market', '市场'],
  ['/news', '新闻'],
  ['/policy', '政策'],
  ['/analysis', '多基金分析'],
  ['/chat', 'AI 对话'],
  ['/reports', '定时报告'],
  ['/settings', '设置'],
];

function pageTitle(pathname: string): string {
  if (pathname.startsWith('/funds/')) return '基金详情';
  for (const [p, t] of TITLES) {
    if (p !== '/' && pathname.startsWith(p)) return t;
  }
  return '仪表盘';
}

function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const unreadCount = useAppStore((s) => s.unreadCount);
  const setUnreadCount = useAppStore((s) => s.setUnreadCount);
  const ref = useRef<HTMLDivElement | null>(null);

  const fetchCount = async () => {
    try {
      const list = await api.get<NotificationItem[]>('/notifications', { unread_only: true });
      setUnreadCount(list.filter((n) => !n.read).length);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    fetchCount();
    const t = window.setInterval(fetchCount, 60_000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .get<NotificationItem[]>('/notifications')
      .then((list) => {
        setItems(list ?? []);
        setUnreadCount((list ?? []).filter((n) => !n.read).length);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const markRead = async (id: number) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setItems((list) => list.map((n) => (n.id === id ? { ...n, read: true } : n)));
      fetchCount();
    } catch {
      /* ignore */
    }
  };

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read-all');
      setItems((list) => list.map((n) => ({ ...n, read: true })));
      fetchCount();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-lg p-2 text-zinc-400 transition hover:bg-white/5 hover:text-zinc-100"
        title="通知"
      >
        <IconBell size={18} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-up px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-96 overflow-hidden rounded-xl border border-white/10 bg-surface shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/5 px-4 py-2.5">
            <span className="text-sm font-semibold text-zinc-100">通知</span>
            <button
              onClick={markAllRead}
              className="text-xs text-accent transition hover:text-blue-300"
            >
              全部已读
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {loading && <div className="p-4 text-center text-xs text-zinc-500">加载中…</div>}
            {!loading && items.length === 0 && (
              <div className="p-6 text-center text-xs text-zinc-500">暂无通知</div>
            )}
            {items.map((n) => (
              <button
                key={n.id}
                onClick={() => markRead(n.id)}
                className={cn(
                  'block w-full border-b border-white/5 px-4 py-3 text-left transition hover:bg-white/[0.03]',
                  !n.read && 'bg-accent/[0.06]',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-zinc-100">{n.title}</span>
                  {!n.read && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-up" />}
                </div>
                {n.content && (
                  <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{n.content}</p>
                )}
                <div className="mt-1 flex items-center justify-between text-[11px] text-zinc-600">
                  <span>{n.type}</span>
                  <span>{timeAgo(n.created_at)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAppStore((s) => s.user);
  const logout = useAppStore((s) => s.logout);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* 侧边栏 */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/5 bg-surface">
        <div className="flex items-center gap-2.5 border-b border-white/5 px-4 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-red-500 to-amber-500 text-sm font-bold text-white shadow-glow">
            基
          </div>
          <div>
            <div className="text-sm font-bold tracking-wide text-zinc-100">基金智能分析平台</div>
            <div className="text-[10px] text-zinc-500">AI Fund Intelligence</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2.5">
          {NAV_ITEMS.map((item) => {
            const active = item.end
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to);
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={cn(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition',
                  active
                    ? 'bg-accent/15 font-medium text-accent'
                    : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-100',
                )}
              >
                <Icon size={16} />
                {item.label}
                {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
              </NavLink>
            );
          })}
        </nav>
        <div className="border-t border-white/5 p-3 text-[10px] leading-relaxed text-zinc-600">
          数据来源：东方财富 / Mock
          <br />
          所有预测仅为概率估计，不构成投资建议
        </div>
      </aside>

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/5 bg-surface/60 px-5 backdrop-blur">
          <div className="text-sm font-medium text-zinc-300">{pageTitle(location.pathname)}</div>
          <div className="flex items-center gap-1.5">
            <NotificationsBell />
            <div className="relative" ref={userRef}>
              <button
                onClick={() => setUserMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition hover:bg-white/5"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-zinc-300">
                  <IconUser size={14} />
                </span>
                <span className="max-w-28 truncate text-sm text-zinc-300">
                  {user?.display_name || user?.username || '用户'}
                </span>
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 top-full z-50 mt-2 w-48 overflow-hidden rounded-xl border border-white/10 bg-surface shadow-2xl">
                  <div className="border-b border-white/5 px-4 py-2.5 text-xs text-zinc-500">
                    {user?.username} · {user?.email || '未绑定邮箱'}
                  </div>
                  <button
                    onClick={() => {
                      setUserMenuOpen(false);
                      navigate('/settings');
                    }}
                    className="block w-full px-4 py-2.5 text-left text-sm text-zinc-300 transition hover:bg-white/5"
                  >
                    设置
                  </button>
                  <button
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-red-400 transition hover:bg-red-500/10"
                  >
                    <IconLogout size={15} /> 退出登录
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-5">
          <Outlet />
        </main>
      </div>
      <ToastHost />
    </div>
  );
}
