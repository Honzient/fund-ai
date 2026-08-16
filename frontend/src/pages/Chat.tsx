import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { ConversationSummary, FundSummary } from '../types/api';
import { useAppStore } from '../store/app';
import { toast } from '../store/toast';
import { cn, timeAgo } from '../utils/format';
import { useDebounce } from '../utils/hooks';
import { Button, Input } from '../components/controls';
import ChatThread, { type FundChip } from '../components/ChatThread';
import { Modal } from '../components/overlay';
import { Skeleton, Spinner } from '../components/ui';
import { IconPlus, IconSearch, IconTrash } from '../components/icons';

function FundPickerModal({
  open,
  onClose,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (f: FundChip) => void;
}) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<FundSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const debounced = useDebounce(search, 350);

  useEffect(() => {
    if (!open) return;
    if (!debounced.trim()) {
      setResults([]);
      return;
    }
    let alive = true;
    setLoading(true);
    api
      .get<FundSummary[]>('/funds', { search: debounced.trim(), limit: 20 })
      .then((list) => {
        if (alive) setResults(list ?? []);
      })
      .catch(() => {
        if (alive) setResults([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [debounced, open]);

  return (
    <Modal open={open} onClose={onClose} title="添加基金到对话" width="max-w-md">
      <div className="relative">
        <IconSearch size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <Input
          value={search}
          onChange={setSearch}
          placeholder="搜索基金名称 / 代码"
          className="pl-9"
        />
      </div>
      <div className="mt-3 max-h-72 space-y-1 overflow-y-auto">
        {loading && (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        )}
        {!loading && results.length === 0 && (
          <div className="py-6 text-center text-xs text-zinc-600">
            {debounced ? '未找到匹配基金' : '输入关键词搜索基金'}
          </div>
        )}
        {results.map((f) => (
          <div
            key={f.fund_code}
            className="flex items-center justify-between rounded-lg border border-white/5 bg-surface-2 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="truncate text-sm text-zinc-100">{f.fund_name}</div>
              <div className="num-mono text-[10px] text-zinc-600">
                {f.fund_code} · {f.fund_type}
              </div>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                onAdd({ code: f.fund_code, name: f.fund_name });
                setSearch('');
                setResults([]);
              }}
            >
              添加
            </Button>
          </div>
        ))}
      </div>
    </Modal>
  );
}

export default function Chat() {
  const [params] = useSearchParams();
  const chatFunds = useAppStore((s) => s.chatFunds);
  const addChatFund = useAppStore((s) => s.addChatFund);
  const removeChatFund = useAppStore((s) => s.removeChatFund);
  const clearChatFunds = useAppStore((s) => s.clearChatFunds);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [convLoading, setConvLoading] = useState(true);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [funds, setFunds] = useState<FundChip[]>([]);

  // 初始化：读取 store 中的基金代码并解析名称
  useEffect(() => {
    const codes = chatFunds;
    if (codes.length === 0) return;
    let alive = true;
    Promise.all(
      codes.map((code) =>
        api
          .get<FundSummary[]>('/funds', { search: code })
          .then((list) => list.find((f) => f.fund_code === code) ?? null)
          .catch(() => null),
      ),
    ).then((found) => {
      if (!alive) return;
      const chips: FundChip[] = found
        .filter((f): f is FundSummary => f !== null)
        .map((f) => ({ code: f.fund_code, name: f.fund_name }));
      setFunds(chips);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 从 ?fund= 参数预选
  useEffect(() => {
    const code = params.get('fund');
    if (code && !chatFunds.includes(code)) {
      api
        .get<FundSummary[]>('/funds', { search: code })
        .then((list) => {
          const f = list.find((x) => x.fund_code === code);
          if (f) {
            addChatFund(f.fund_code);
            setFunds((prev) => [...prev, { code: f.fund_code, name: f.fund_name }]);
          }
        })
        .catch(() => {
          /* ignore */
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // 会话列表
  const loadConversations = () => {
    setConvLoading(true);
    api
      .get<ConversationSummary[]>('/chat/conversations')
      .then((list) => setConversations(list ?? []))
      .catch(() => setConversations([]))
      .finally(() => setConvLoading(false));
  };

  useEffect(() => {
    loadConversations();
  }, []);

  const newConversation = async () => {
    try {
      const res = await api.post<ConversationSummary>('/chat/conversations', {});
      setConversations((list) => [res, ...list]);
      setConversationId(res.id);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '创建会话失败', 'error');
    }
  };

  const deleteConversation = async (id: string) => {
    try {
      await api.delete(`/chat/conversations/${id}`);
      setConversations((list) => list.filter((c) => c.id !== id));
      if (conversationId === id) setConversationId(null);
      toast('会话已删除', 'info');
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '删除失败', 'error');
    }
  };

  const addFund = (chip: FundChip) => {
    addChatFund(chip.code);
    setFunds((prev) => (prev.some((f) => f.code === chip.code) ? prev : [...prev, chip]));
    setPickerOpen(false);
  };

  const removeFund = (code: string) => {
    removeChatFund(code);
    setFunds((prev) => prev.filter((f) => f.code !== code));
  };

  const sortedConversations = useMemo(
    () => conversations.slice().sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')),
    [conversations],
  );

  return (
    <div className="flex h-[calc(100vh-96px)] gap-4">
      {/* 会话列表 */}
      <div className="flex w-60 shrink-0 flex-col rounded-xl border border-white/5 bg-surface">
        <div className="flex items-center justify-between border-b border-white/5 p-3">
          <span className="text-sm font-semibold text-zinc-100">会话</span>
          <button
            onClick={() => void newConversation()}
            className="flex items-center gap-1 rounded-md bg-accent/15 px-2 py-1 text-xs font-medium text-accent transition hover:bg-accent/25"
          >
            <IconPlus size={12} /> 新会话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {convLoading && (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}
          {!convLoading && sortedConversations.length === 0 && (
            <div className="px-3 py-8 text-center text-xs text-zinc-600">
              暂无会话
              <br />
              点击「新会话」开始
            </div>
          )}
          <div className="space-y-1">
            {sortedConversations.map((c) => (
              <div
                key={c.id}
                className={cn(
                  'group relative cursor-pointer rounded-lg px-3 py-2.5 transition',
                  conversationId === c.id ? 'bg-accent/12' : 'hover:bg-white/5',
                )}
                onClick={() => setConversationId(c.id)}
              >
                <div
                  className={cn(
                    'truncate pr-6 text-sm',
                    conversationId === c.id ? 'text-accent' : 'text-zinc-200',
                  )}
                >
                  {c.title || '新对话'}
                </div>
                <div className="mt-0.5 truncate text-[10px] text-zinc-600">
                  {c.last_message || '暂无消息'} · {timeAgo(c.updated_at)}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    void deleteConversation(c.id);
                  }}
                  className="absolute right-2 top-2 hidden rounded p-1 text-zinc-600 transition hover:text-red-400 group-hover:block"
                >
                  <IconTrash size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 对话主区 */}
      <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-white/5 bg-surface">
        {/* 基金 chips */}
        <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-white/5 px-4 py-2.5">
          <span className="shrink-0 text-[11px] text-zinc-500">对话基金：</span>
          {funds.map((f) => (
            <span
              key={f.code}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-accent"
            >
              <span className="num-mono">{f.code}</span>
              <span className="max-w-24 truncate">{f.name}</span>
              <button
                onClick={() => removeFund(f.code)}
                className="text-accent/60 transition hover:text-red-400"
              >
                ✕
              </button>
            </span>
          ))}
          <button
            onClick={() => setPickerOpen(true)}
            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-white/10 px-2.5 py-1 text-xs text-zinc-400 transition hover:border-accent/50 hover:text-accent"
          >
            <IconPlus size={12} /> 添加基金
          </button>
          {funds.length > 0 && (
            <button
              onClick={() => {
                clearChatFunds();
                setFunds([]);
              }}
              className="shrink-0 text-[11px] text-zinc-600 transition hover:text-zinc-300"
            >
              清空
            </button>
          )}
        </div>

        {/* 消息线程 */}
        <div className="min-h-0 flex-1 px-4">
          <ChatThread
            key={conversationId ?? 'new'}
            funds={funds}
            conversationId={conversationId}
            onNewConversation={(id) => {
              setConversationId(id);
              loadConversations();
            }}
            height="100%"
          />
        </div>
      </div>

      <FundPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} onAdd={addFund} />
    </div>
  );
}
