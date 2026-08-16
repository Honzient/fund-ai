import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { MultiAnalysisResponse, WatchlistItem } from '../types/api';
import { useAppStore } from '../store/app';
import { toast } from '../store/toast';
import { cn, formatPct, pctColor } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Button, Checkbox, Segmented, Select } from '../components/controls';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, Spinner } from '../components/ui';
import { ScoreBadge, TrendBadge } from '../components/badges';
import RadarChart from '../components/RadarChart';

const TIME_RANGES = [
  { value: '1M', label: '1月' },
  { value: '3M', label: '3月' },
  { value: '6M', label: '6月' },
  { value: '1Y', label: '1年' },
];

const BREAKDOWN_LABELS: Record<string, string> = {
  trend: '趋势',
  volatility: '波动',
  risk: '风险',
  quality: '质量',
  macro: '宏观',
  industry: '行业',
  sentiment: '情绪',
};

export default function Analysis() {
  const navigate = useNavigate();
  const watchlistVersion = useAppStore((s) => s.watchlistVersion);
  const watchlist = useApi<WatchlistItem[]>(() => api.get('/watchlist'), [watchlistVersion]);

  const [selected, setSelected] = useState<string[]>([]);
  const [timeRange, setTimeRange] = useState('3M');
  const [result, setResult] = useState<MultiAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (code: string) => {
    setSelected((s) => (s.includes(code) ? s.filter((c) => c !== code) : [...s, code]));
  };

  const run = async () => {
    if (selected.length === 0) {
      toast('请至少选择一只基金', 'error');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<MultiAnalysisResponse>('/analysis', {
        fund_ids: selected,
        time_range: timeRange,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '分析请求失败');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const selectedNames = useMemo(() => {
    const items = watchlist.data ?? [];
    return selected.map((code) => items.find((w) => w.fund.fund_code === code)?.fund.fund_name ?? code);
  }, [selected, watchlist.data]);

  const radarSeries = useMemo(() => {
    if (!result) return [];
    const palette = ['#3b82f6', '#f59e0b', '#a78bfa', '#34d399', '#f472b6', '#22d3ee'];
    return result.funds
      .filter((f) => f.score_breakdown && Object.keys(f.score_breakdown).length > 0)
      .map((f, i) => ({
        name: f.fund.fund_name,
        data: Object.keys(f.score_breakdown ?? {}).map((k) => f.score_breakdown![k] ?? 0),
        color: palette[i % palette.length],
      }));
  }, [result]);

  const radarIndicators = useMemo(() => {
    const keys = result?.funds.find((f) => f.score_breakdown)?.score_breakdown
      ? Object.keys(result.funds.find((f) => f.score_breakdown)!.score_breakdown!)
      : [];
    return keys.map((k) => ({ name: BREAKDOWN_LABELS[k] ?? k, max: 100 }));
  }, [result]);

  const comparison = result?.comparison;

  return (
    <div className="space-y-4">
      <PageHeader
        title="多基金分析"
        desc="对多只自选基金进行评分、风险与收益横向对比"
      />

      {/* 选择区 */}
      <Card title="选择基金">
        {watchlist.loading && <Skeleton className="h-24 w-full" />}
        {watchlist.error && <ErrorState message={watchlist.error} onRetry={watchlist.reload} />}
        {!watchlist.loading && (watchlist.data ?? []).length === 0 && (
          <EmptyState
            title="自选列表为空"
            desc="请先在「基金」页添加自选基金"
            icon="⭐"
            action={
              <Button variant="primary" size="sm" onClick={() => navigate('/funds')}>
                去添加自选
              </Button>
            }
          />
        )}
        {!watchlist.loading && (watchlist.data ?? []).length > 0 && (
          <div className="flex flex-wrap gap-2">
            {(watchlist.data ?? []).map((w) => (
              <label
                key={w.id}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 transition',
                  selected.includes(w.fund.fund_code)
                    ? 'border-accent/60 bg-accent/10'
                    : 'border-white/10 hover:border-white/20',
                )}
              >
                <Checkbox
                  checked={selected.includes(w.fund.fund_code)}
                  onChange={() => toggle(w.fund.fund_code)}
                />
                <div>
                  <div className="text-xs font-medium text-zinc-100">{w.fund.fund_name}</div>
                  <div className="num-mono text-[10px] text-zinc-600">{w.fund.fund_code}</div>
                </div>
              </label>
            ))}
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-white/5 pt-4">
          <span className="text-xs text-zinc-500">分析区间：</span>
          <Segmented value={timeRange} onChange={setTimeRange} options={TIME_RANGES} />
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void run()}
              disabled={loading || selected.length === 0}
            >
              {loading ? <Spinner className="h-4 w-4" /> : `开始分析（${selected.length} 只）`}
            </Button>
          </div>
        </div>
      </Card>

      {error && <ErrorState message={error} onRetry={() => void run()} />}

      {loading && (
        <Card title="分析中…">
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </Card>
      )}

      {!loading && result && (
        <>
          {/* 对比表 */}
          <Card title="横向对比">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-white/5 text-[11px] text-zinc-500">
                    <th className="py-2 pr-3 font-medium">基金</th>
                    <th className="px-3 py-2 text-center font-medium">评分</th>
                    <th className="px-3 py-2 text-right font-medium">Sharpe</th>
                    <th className="px-3 py-2 text-right font-medium">最大回撤</th>
                    <th className="px-3 py-2 text-right font-medium">年化波动</th>
                    <th className="px-3 py-2 text-right font-medium">1月收益</th>
                    <th className="px-3 py-2 text-right font-medium">3月收益</th>
                    <th className="px-3 py-2 text-center font-medium">短期</th>
                    <th className="px-3 py-2 text-center font-medium">中期</th>
                    <th className="px-3 py-2 text-center font-medium">长期</th>
                  </tr>
                </thead>
                <tbody>
                  {(comparison?.table ?? []).map((row) => (
                    <tr
                      key={row.fund_code}
                      className={cn(
                        'border-b border-white/5 transition hover:bg-white/[0.03]',
                        comparison?.highest_score === row.fund_code && 'bg-gold/[0.04]',
                      )}
                    >
                      <td className="py-2.5 pr-3">
                        <button
                          onClick={() => navigate(`/funds/${row.fund_code}`)}
                          className="block max-w-48 truncate text-left text-zinc-100 hover:text-accent"
                        >
                          {row.fund_name}
                        </button>
                        <div className="num-mono text-[10px] text-zinc-600">{row.fund_code}</div>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <ScoreBadge score={row.score} />
                      </td>
                      <td className="num-mono px-3 py-2.5 text-right text-zinc-200">
                        {row.sharpe !== null && row.sharpe !== undefined ? row.sharpe.toFixed(2) : '--'}
                      </td>
                      <td className="num-mono px-3 py-2.5 text-right text-down">
                        {row.max_drawdown !== null && row.max_drawdown !== undefined ? `${row.max_drawdown.toFixed(2)}%` : '--'}
                      </td>
                      <td className="num-mono px-3 py-2.5 text-right text-zinc-200">
                        {row.annual_volatility !== null && row.annual_volatility !== undefined
                          ? `${row.annual_volatility.toFixed(2)}%`
                          : '--'}
                      </td>
                      <td className={cn('num-mono px-3 py-2.5 text-right', pctColor(row.return_1m))}>
                        {formatPct(row.return_1m)}
                      </td>
                      <td className={cn('num-mono px-3 py-2.5 text-right', pctColor(row.return_3m))}>
                        {formatPct(row.return_3m)}
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <TrendBadge trend={row.trend_short} />
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <TrendBadge trend={row.trend_medium} />
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <TrendBadge trend={row.trend_long} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {comparison && (comparison.best_trend || comparison.lowest_risk || comparison.highest_score) && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-white/5 pt-3 text-[11px] text-zinc-500">
                {comparison.highest_score && (
                  <span>
                    最高评分：<span className="num-mono text-gold">{comparison.highest_score}</span>
                  </span>
                )}
                {comparison.best_trend && (
                  <span>
                    趋势最佳：<span className="num-mono text-up">{comparison.best_trend}</span>
                  </span>
                )}
                {comparison.lowest_risk && (
                  <span>
                    风险最低：<span className="num-mono text-down">{comparison.lowest_risk}</span>
                  </span>
                )}
              </div>
            )}
            <div className="mt-2 text-[10px] text-zinc-600">生成时间：{result.generated_at ?? '--'}</div>
          </Card>

          {/* 雷达图 */}
          <Card title="评分维度雷达对比">
            {radarSeries.length > 0 ? (
              <RadarChart indicators={radarIndicators} series={radarSeries} height={360} />
            ) : (
              <EmptyState title="无评分维度数据" icon="🕸️" />
            )}
          </Card>

          {/* 每只基金的因子 */}
          <div className="grid gap-3 lg:grid-cols-2">
            {result.funds.map((f) => (
              <Card key={f.fund.fund_code} title={`${f.fund.fund_name}（${f.fund.fund_code}）`}>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <ScoreBadge score={f.score} />
                  <span className="text-[11px] text-zinc-600">区间 {f.time_range}</span>
                </div>
                <div className="space-y-3">
                  {f.positive_factors.length > 0 && (
                    <div>
                      <div className="mb-1.5 text-xs font-semibold text-up">积极因素</div>
                      <ul className="space-y-1">
                        {f.positive_factors.map((x, i) => (
                          <li key={i} className="text-xs leading-relaxed text-zinc-400">
                            <span className="text-zinc-200">{x.factor}</span>
                            {x.reason && ` — ${x.reason}`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {f.negative_factors.length > 0 && (
                    <div>
                      <div className="mb-1.5 text-xs font-semibold text-down">消极因素</div>
                      <ul className="space-y-1">
                        {f.negative_factors.map((x, i) => (
                          <li key={i} className="text-xs leading-relaxed text-zinc-400">
                            <span className="text-zinc-200">{x.factor}</span>
                            {x.reason && ` — ${x.reason}`}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {f.main_risks.length > 0 && (
                    <div>
                      <div className="mb-1.5 text-xs font-semibold text-zinc-300">主要风险</div>
                      <ul className="space-y-1">
                        {f.main_risks.map((r, i) => (
                          <li key={i} className="text-xs text-zinc-400">
                            <span className="text-zinc-200">{r.category}</span>：{r.detail}（{r.severity}）
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {f.positive_factors.length === 0 && f.negative_factors.length === 0 && (
                    <div className="text-xs text-zinc-600">该基金未返回因子分析</div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {!loading && !result && !error && (
        <Card>
          <EmptyState
            title="选择基金后开始分析"
            desc="系统将对比评分、Sharpe、回撤、波动、收益与趋势，并叠加评分维度雷达图"
            icon="🧮"
          />
        </Card>
      )}
    </div>
  );
}
