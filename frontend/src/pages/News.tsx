import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { NewsItem } from '../types/api';
import { cn, formatDateTime, timeAgo } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Select } from '../components/controls';
import { LevelBadge, SentimentBadge } from '../components/badges';
import { Modal } from '../components/overlay';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui';

export default function News() {
  const [params] = useSearchParams();
  const focusId = params.get('focus') ? Number(params.get('focus')) : null;
  const [industry, setIndustry] = useState('');
  const [importance, setImportance] = useState('');
  const [detail, setDetail] = useState<NewsItem | null>(null);

  const news = useApi<NewsItem[]>(
    () =>
      api
        .get<{ items: NewsItem[] }>('/news', {
          limit: 100,
          ...(industry ? { industry } : {}),
          ...(importance ? { min_importance: importance } : {}),
        })
        .then((r) => r.items),
    [industry, importance],
  );

  const industries = useMemo(() => {
    const set = new Set<string>();
    (news.data ?? []).forEach((n) => {
      if (n.related_industry) set.add(n.related_industry);
    });
    return Array.from(set).sort();
  }, [news.data]);

  const focusItem = useMemo(
    () => focusId && news.data ? news.data.find((n) => n.id === focusId) ?? null : null,
    [focusId, news.data],
  );

  return (
    <div className="space-y-4">
      <PageHeader title="新闻" desc="行业新闻与市场情绪（带情绪与重要度标注）" />

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={industry}
          onChange={setIndustry}
          options={[{ value: '', label: '全部行业' }, ...industries.map((i) => ({ value: i, label: i }))]}
        />
        <Select
          value={importance}
          onChange={setImportance}
          options={[
            { value: '', label: '全部重要度' },
            { value: '0.66', label: '高重要度' },
            { value: '0.33', label: '中重要度' },
          ]}
        />
        <span className="text-[11px] text-zinc-600">共 {news.data?.length ?? 0} 条</span>
      </div>

      <Card bodyClassName="p-0">
        {news.loading && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}
        {news.error && <ErrorState message={news.error} onRetry={news.reload} />}
        {!news.loading && (news.data ?? []).length === 0 && (
          <EmptyState title="暂无新闻" desc="后端新闻数据不可用或筛选无结果" icon="📰" />
        )}
        <div className="divide-y divide-white/5">
          {(news.data ?? [])
            .slice()
            .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0))
            .map((n) => (
              <button
                key={n.id}
                onClick={() => setDetail(n)}
                className="block w-full px-4 py-3.5 text-left transition hover:bg-white/[0.03]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-100">{n.title}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-600">
                      <span>{n.source ?? '--'}</span>
                      {n.related_industry && <span>· {n.related_industry}</span>}
                      {n.related_fund && <span className="num-mono">· 基金 {n.related_fund}</span>}
                      <span>· {timeAgo(n.published_at)}</span>
                    </div>
                    {n.content && (
                      <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-zinc-500">
                        {n.content}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <SentimentBadge label={n.sentiment_label} value={n.sentiment} />
                    <LevelBadge value={n.importance} label="重要度" />
                  </div>
                </div>
              </button>
            ))}
        </div>
      </Card>

      {/* 详情 */}
      {(detail || focusItem) && (
        <NewsDetailModal
          item={detail ?? focusItem!}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

function NewsDetailModal({ item, onClose }: { item: NewsItem; onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title="新闻详情" width="max-w-2xl">
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-zinc-50">{item.title}</h2>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
          <span>{item.source ?? '--'}</span>
          <span>{formatDateTime(item.published_at)}</span>
          <SentimentBadge label={item.sentiment_label} value={item.sentiment} />
          <LevelBadge value={item.importance} label="重要度" />
          {item.related_industry && <span>行业：{item.related_industry}</span>}
          {item.related_fund && <span className="num-mono">相关基金：{item.related_fund}</span>}
        </div>
        {item.url && (
          <a href={item.url} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline">
            查看原文链接 ↗
          </a>
        )}
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
          {item.content ?? '（无正文内容）'}
        </p>
        <div className="border-t border-white/5 pt-2 text-[10px] text-zinc-600">
          抓取时间：{formatDateTime(item.retrieved_at)} · 情绪值 {item.sentiment ?? '--'}
        </div>
      </div>
    </Modal>
  );
}
