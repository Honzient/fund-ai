import { useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { ChatResponse, ConversationDetail, ConversationSources } from '../types/api';
import { cn, formatDateTime } from '../utils/format';
import Markdown from './Markdown';
import { Badge } from './badges';
import { Modal } from './overlay';
import { Spinner } from './ui';
import { IconRobot, IconSend } from './icons';

export interface FundChip {
  code: string;
  name: string;
}

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string | null;
  model?: string | null;
  fallback?: boolean;
  convId?: string | null;
  error?: boolean;
  loading?: boolean;
}

interface ChatThreadProps {
  funds: FundChip[];
  /** 外部控制的会话 id；null 表示新会话（父组件用 key 强制重置） */
  conversationId?: string | null;
  onNewConversation?: (id: string) => void;
  height?: string;
  embedded?: boolean;
}

const SUGGESTIONS = [
  '这只基金最近表现如何？',
  '分析一下短期趋势和风险',
  '当前市场环境适合加仓吗？（请客观分析）',
  '对比一下这只基金与同类基金的表现',
];

function SourcesModal({
  conversationId,
  onClose,
}: {
  conversationId: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<ConversationSources | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .get<ConversationSources>(`/chat/conversations/${conversationId}/sources`)
      .then((d) => {
        if (alive) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e: unknown) => {
        if (alive) {
          setError(e instanceof ApiError ? e.message : String(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [conversationId]);

  const rows = useMemo(() => {
    if (!data) return [];
    const list: { label: string; value: string; tone?: 'red' | 'green' | 'zinc' }[] = [];
    const funds = data['funds'];
    if (Array.isArray(funds)) {
      list.push({
        label: '基金数据',
        value: funds
          .map((f) => {
            const o = f as { fund_code?: string; fund_name?: string };
            return o.fund_name ? `${o.fund_name}（${o.fund_code ?? ''}）` : JSON.stringify(f);
          })
          .join('、') || '--',
      });
    }
    const boolRow = (label: string, key: string) => {
      const v = data[key];
      if (v === undefined) return;
      list.push({
        label,
        value: v ? '已注入' : '未注入',
        tone: v ? 'red' : 'zinc',
      });
    };
    boolRow('行情数据', 'market');
    boolRow('宏观数据', 'macro');
    boolRow('预测数据', 'prediction');
    const newsCount = data['news_count'];
    if (typeof newsCount === 'number') list.push({ label: '注入新闻', value: `${newsCount} 条` });
    const polCount = data['policies_count'];
    if (typeof polCount === 'number') list.push({ label: '注入政策', value: `${polCount} 条` });
    const asOf = data['data_as_of'];
    if (typeof asOf === 'string') list.push({ label: '数据截止', value: asOf });
    const retr = data['retrieved_at'];
    if (typeof retr === 'string') list.push({ label: '数据获取时间', value: formatDateTime(retr) });
    const ver = data['context_version'];
    if (typeof ver === 'number') list.push({ label: 'Context 版本', value: `v${ver}` });
    return list;
  }, [data]);

  return (
    <Modal open onClose={onClose} title="本次分析数据来源" width="max-w-md">
      {loading && (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      )}
      {error && <div className="py-8 text-center text-sm text-red-400">{error}</div>}
      {!loading && !error && (
        <div className="space-y-2">
          {rows.length === 0 && (
            <div className="py-6 text-center text-sm text-zinc-500">暂无数据来源信息</div>
          )}
          {rows.map((r) => (
            <div
              key={r.label}
              className="flex items-center justify-between rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5"
            >
              <span className="text-xs text-zinc-400">{r.label}</span>
              <span
                className={cn(
                  'text-sm font-medium',
                  r.tone === 'red' ? 'text-up' : r.tone === 'green' ? 'text-down' : 'text-zinc-200',
                )}
              >
                {r.value}
              </span>
            </div>
          ))}
          <p className="pt-2 text-[11px] leading-relaxed text-zinc-600">
            所有注入上下文均可在后端数据来源表（source / retrieved_at）中追溯，确保分析透明可验证。
          </p>
        </div>
      )}
    </Modal>
  );
}

/** 消息流 + 输入框（/chat 页与基金详情内嵌共用） */
export default function ChatThread({
  funds,
  conversationId,
  onNewConversation,
  height = '100%',
  embedded = false,
}: ChatThreadProps) {
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sourcesConv, setSourcesConv] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const idRef = useRef(0);

  const nextId = () => `m${++idRef.current}-${Date.now()}`;

  // 切换会话时加载
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    let alive = true;
    api
      .get<ConversationDetail>(`/chat/conversations/${conversationId}`)
      .then((d) => {
        if (!alive) return;
        setMessages(
          (d.messages ?? []).map((m) => ({
            id: nextId(),
            role: m.role,
            content: m.content,
            created_at: m.created_at,
            model: m.model,
            convId: conversationId,
          })),
        );
      })
      .catch(() => {
        if (alive) setMessages([]);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  // 自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    const userMsg: LocalMessage = { id: nextId(), role: 'user', content, created_at: new Date().toISOString() };
    const pending: LocalMessage = {
      id: nextId(),
      role: 'assistant',
      content: '',
      loading: true,
      created_at: new Date().toISOString(),
      convId: conversationId ?? null,
    };
    setMessages((m) => [...m, userMsg, pending]);
    setInput('');
    setSending(true);
    try {
      const res = await api.post<ChatResponse>('/chat', {
        message: content,
        fund_ids: funds.map((f) => f.code),
        ...(conversationId ? { conversation_id: conversationId } : {}),
      });
      const convId = res.conversation_id;
      if (!conversationId && convId && onNewConversation) {
        onNewConversation(convId);
      }
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pending.id
            ? {
                ...msg,
                content: res.reply ?? '（空回复）',
                loading: false,
                model: res.model,
                fallback: res.fallback,
                convId: convId || conversationId || null,
              }
            : msg,
        ),
      );
    } catch (e) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pending.id
            ? {
                ...msg,
                content: e instanceof ApiError ? `请求失败：${e.message}` : '请求失败，请稍后重试',
                loading: false,
                error: true,
              }
            : msg,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 消息流 */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-1 py-3">
        {messages.length === 0 && !sending && (
          <div className="flex h-full flex-col items-center justify-center gap-4 py-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent">
              <IconRobot size={24} />
            </div>
            <div className="text-sm text-zinc-400">
              {funds.length > 0
                ? `已关联 ${funds.map((f) => f.name).join('、')}，向我提问吧`
                : '选择基金后，我可以基于行情、技术指标、宏观、新闻与预测数据回答'}
            </div>
            {!embedded && (
              <div className="flex max-w-md flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className="rounded-full border border-white/10 bg-surface-2 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-accent/50 hover:text-accent"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.map((m) =>
          m.role === 'user' ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[78%] rounded-2xl rounded-tr-sm bg-accent/90 px-3.5 py-2.5 text-sm leading-relaxed text-white">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={m.id} className="flex justify-start">
              <div className="max-w-[85%]">
                <div className="rounded-2xl rounded-tl-sm border border-white/8 bg-surface-2 px-3.5 py-2.5">
                  {m.loading ? (
                    <div className="flex items-center gap-2 py-1 text-sm text-zinc-500">
                      <Spinner className="h-3.5 w-3.5" /> 正在生成回答…
                    </div>
                  ) : (
                    <Markdown content={m.content} />
                  )}
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 px-1 text-[11px] text-zinc-600">
                  {m.model && <span className="font-mono">{m.model}</span>}
                  {m.fallback && (
                    <Badge tone="amber">量化引擎摘要（LLM 不可用）</Badge>
                  )}
                  {m.convId && !m.loading && (
                    <button
                      onClick={() => setSourcesConv(m.convId!)}
                      className="text-accent transition hover:text-blue-300"
                    >
                      数据来源
                    </button>
                  )}
                  {m.created_at && <span>{formatDateTime(m.created_at)}</span>}
                </div>
              </div>
            </div>
          ),
        )}
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-white/5 pt-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            className="max-h-32 flex-1 resize-none rounded-lg border border-white/10 bg-surface-2 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-accent/60"
          />
          <button
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
            title="发送"
          >
            <IconSend size={16} />
          </button>
        </div>
      </div>

      {sourcesConv && <SourcesModal conversationId={sourcesConv} onClose={() => setSourcesConv(null)} />}
    </div>
  );
}
