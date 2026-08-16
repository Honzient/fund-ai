import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { IndexHistoryResponse, MarketIndex, MarketOverview } from '../types/api';
import { toast } from '../store/toast';
import { cn, formatDateTime, formatPct, pctColor } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui';
import { Segmented } from '../components/controls';
import KlineChart, { type KlinePeriod } from '../components/KlineChart';
import { IconRefresh } from '../components/icons';

export default function Market() {
  const [params] = useSearchParams();
  const [indexCode, setIndexCode] = useState(params.get('index') ?? '');
  const [period, setPeriod] = useState<KlinePeriod>('daily');
  const [syncing, setSyncing] = useState(false);

  const indexes = useApi<MarketIndex[]>(() => api.get('/market/indexes'), []);
  const overview = useApi<MarketOverview>(() => api.get('/market/overview'), []);

  useEffect(() => {
    if (!indexCode && (indexes.data ?? []).length > 0) {
      setIndexCode(indexes.data![0].index_code);
    }
  }, [indexes.data, indexCode]);

  const history = useApi<IndexHistoryResponse>(
    () => api.get(`/market/indexes/${indexCode}/history`, { period }),
    [indexCode, period],
    { enabled: !!indexCode },
  );

  const current = useMemo(
    () => (indexes.data ?? []).find((i) => i.index_code === indexCode),
    [indexes.data, indexCode],
  );

  const sync = async () => {
    setSyncing(true);
    try {
      const res = await api.post<{ task_id: string; status: string }>('/market/sync');
      toast(`已提交行情同步任务（${res.task_id}）`, 'success');
      window.setTimeout(() => {
        indexes.reload();
        overview.reload();
        history.reload();
      }, 1500);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '同步失败', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const regime = overview.data?.market_regime;

  return (
    <div className="space-y-4">
      <PageHeader
        title="市场行情"
        desc="主要指数行情、K 线与市场环境判断"
        extra={
          <button
            onClick={() => void sync()}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition hover:bg-accent/20 disabled:opacity-50"
          >
            <IconRefresh size={13} className={syncing ? 'animate-spin' : ''} />
            {syncing ? '提交中…' : '同步行情'}
          </button>
        }
      />

      {/* 指数卡片 */}
      {indexes.loading && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}
      {indexes.error && <ErrorState message={indexes.error} onRetry={indexes.reload} />}
      {!indexes.loading && (indexes.data ?? []).length > 0 && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          {(indexes.data ?? []).map((idx) => (
            <button
              key={idx.index_code}
              onClick={() => setIndexCode(idx.index_code)}
              className={cn(
                'card p-3 text-left transition',
                indexCode === idx.index_code ? 'border-accent/60 bg-accent/[0.06]' : 'hover:border-white/15',
              )}
            >
              <div className="truncate text-xs text-zinc-400">{idx.index_name}</div>
              <div className="num-mono mt-1.5 text-lg font-semibold text-zinc-100">
                {idx.latest_close !== null && idx.latest_close !== undefined ? idx.latest_close.toFixed(2) : '--'}
              </div>
              <div className={cn('num-mono mt-0.5 text-xs font-medium', pctColor(idx.change_pct))}>
                {formatPct(idx.change_pct)}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* 图表 + 环境 */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title={current ? `${current.index_name} K 线` : '指数 K 线'}
          extra={
            current?.data_time ? (
              <span className="text-[11px] text-zinc-600">{formatDateTime(current.data_time)}</span>
            ) : undefined
          }
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] text-zinc-600">
              {history.data?.count ?? 0} 个数据点 · {history.data?.data_status === 'estimate' ? '盘中估值' : '最新可用数据'}
            </span>
          </div>
          <KlineChart
            data={(history.data?.items ?? []).map((i) => ({
              date: i.date,
              open: i.open,
              high: i.high,
              low: i.low,
              close: i.close,
              volume: i.volume,
            }))}
            loading={history.loading}
            name="指数"
            period={period}
            onPeriodChange={setPeriod}
            height={440}
            emptyText="暂无指数行情数据"
          />
        </Card>

        <Card title="市场环境判断">
          {overview.loading && <Skeleton className="h-48 w-full" />}
          {overview.error && <ErrorState message={overview.error} onRetry={overview.reload} />}
          {!overview.loading && !regime && (
            <EmptyState title="暂无市场环境数据" desc="market/overview 未返回 market_regime" icon="🧭" />
          )}
          {regime && (
            <div className="space-y-4">
              <div>
                <div className="text-lg font-bold text-zinc-100">{regime.label}</div>
                <div className="mt-1 text-[11px] text-zinc-500">市场环境评分</div>
                <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-blue-500 to-red-500"
                    style={{ width: `${Math.min(100, Math.max(2, regime.score ?? 0))}%` }}
                  />
                </div>
                <div className="num-mono mt-1 text-right text-xs text-accent">
                  {Math.round(regime.score ?? 0)} / 100
                </div>
              </div>
              <div>
                <div className="mb-2 text-[11px] text-zinc-500">驱动因素</div>
                <ul className="space-y-1.5">
                  {(regime.drivers ?? []).map((d, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-zinc-300">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                      {d}
                    </li>
                  ))}
                  {(regime.drivers ?? []).length === 0 && (
                    <li className="text-xs text-zinc-600">暂无驱动因素</li>
                  )}
                </ul>
              </div>
              {overview.data?.generated_at && (
                <div className="border-t border-white/5 pt-2 text-[10px] text-zinc-600">
                  生成时间：{formatDateTime(overview.data.generated_at)}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
