import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types/api';

interface AppState {
  token: string | null;
  user: User | null;
  /** 自选列表版本号，变化时相关页面刷新 */
  watchlistVersion: number;
  /** 未读通知数 */
  unreadCount: number;
  /** AI 对话当前选中的基金代码 */
  chatFunds: string[];
  setAuth: (token: string, user: User) => void;
  setUser: (user: User) => void;
  logout: () => void;
  bumpWatchlist: () => void;
  setUnreadCount: (n: number) => void;
  addChatFund: (code: string) => void;
  removeChatFund: (code: string) => void;
  clearChatFunds: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      watchlistVersion: 0,
      unreadCount: 0,
      chatFunds: [],
      setAuth: (token, user) => set({ token, user }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, user: null, chatFunds: [] }),
      bumpWatchlist: () => set((s) => ({ watchlistVersion: s.watchlistVersion + 1 })),
      setUnreadCount: (n) => set({ unreadCount: n }),
      addChatFund: (code) =>
        set((s) =>
          s.chatFunds.includes(code) ? s : { chatFunds: [...s.chatFunds, code] },
        ),
      removeChatFund: (code) =>
        set((s) => ({ chatFunds: s.chatFunds.filter((c) => c !== code) })),
      clearChatFunds: () => set({ chatFunds: [] }),
    }),
    { name: 'fund-app-storage' },
  ),
);
