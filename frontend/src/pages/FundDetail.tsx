import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type {
  FundAnalysisResponse,
  FundDetail,
  HoldingsResponse,
  IndexHistoryResponse,
  IndicatorsResponse,
  LedgerResponse,
  MarketIndex,
  NavHistoryResponse,
  NewsItem,
  PolicyItem,
  PredictionResponse,
  RiskResponse,
} from '../types/api';
import { toast } from '../store/toast';
import { cn, compactCN, formatDate, formatDateTime, formatNum, formatPct, pctColor } from '../utils/format';
import { maxDrawdown } from '../utils/indicators';
import { useApi } from '../utils/hooks';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui';
import { Segmented } from '../components/controls';
import {
  ConfidenceBadge,
  DataStatusBadge,
  RiskLevelBadge,
  ScoreBadge,
  SeverityBadge,
  TrendBadge,
} from '../components/badges';
import KlineChart, { type KlinePeriod } from '../components/KlineChart';
import NavChart from '../components/NavChart';
import Gauge from '../components/Gauge';
import RadarChart from '../components/RadarChart';
import Markdown from '../components/Markdown';
import ChatThread, { type FundChip } from '../components/ChatThread';
import { Modal } from '../components/overlay';
import { IconRefresh } from '../components/icons';
import { ACCENT, GOLD } from '../utils/chart';

type RangeKey = '1M' | '3M' | '6M' | '1Y' | '3Y' | 'ALL';
const RANGE_DAYS: Record<Exclude<RangeKey, 'ALL'>, number> = {
  '1M': 31,
  '3M': 92,
  '6M': 184,
  '1Y': 366,
  '3Y': 1098,
};

function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const TABS = ['走势图', '技术指标', '风险指标', '持仓', 'AI分析', '预测历史', '新闻', '政策', 'AI对话'] as const;
type TabKey = (typeof TABS)[number];

// ---------- Tab: 走势图 ----------
function TrendTab({ code, history, period }: { code: string; history: NavHistoryResponse | null; period: KlinePeriod }) {
  const [benchmark, setBenchmark] = useState('');
  const indexes = useApi<MarketIndex[]>(() => api.get('/market/indexes'), []);
  const risk = useApi<RiskResponse>(() => api.get(`/funds/${code}/risk`), [code]);

  useEffect(() => {
    if (!benchmark && (indexes.data ?? []).length > 0) {
      setBenchmark(indexes.data![0].index_code);
    }
  }, [indexes.data, benchmark]);

  const benchHistory = useApi<IndexHistoryResponse>(
    () =>
      api.get(`/market/indexes/${benchmark}/history`, {
        period,
        limit: 400,
      }),
    [benchmark, period],
    { enabled: !!benchmark },
  );

  const { fundReturn, benchReturn, excess } = useMemo(() => {
    const items = history?.items ?? [];
    const navs = items.map((i) => i.nav).filter((v): v is number => v !== null && v !== undefined);
    const fundReturn = navs.length >= 2 ? ((navs[navs.length - 1] / navs[0] - 1) * 100) : 0;
    const bItems = benchHistory.data?.items ?? [];
    const closes = bItems.map((i) => i.close).filter((v): v is number => v !== null && v !== undefined);
    const benchReturn = closes.length >= 2 ? ((closes[closes.length - 1] / closes[0] - 1) * 100) : 0;
    return { fundReturn, benchReturn, excess: fundReturn - benchReturn };
  }, [history, benchHistory.data]);

  const navSeries = useMemo(() => {
    const items = history?.items ?? [];
    return items
      .map((i) => [i.date, i.nav] as [string, number | null])
      .filter(([, v]) => v !== null);
  }, [history]);

  const benchSeries = useMemo(() => {
    const items = benchHistory.data?.items ?? [];
    return items
      .map((i) => [i.date, i.close] as [string, number | null])
      .filter(([, v]) => v !== null);
  }, [benchHistory.data]);

  const metrics = risk.data?.metrics;

  return (
    <div className="space-y-4">
      <Card
        title="净值 K 线（MA5/10/20/60 · 成交量 · MACD · RSI）"
        extra={
          <span className="text-[11px] text-zinc-600">
            {history?.data_status === 'estimate' ? '盘中估值' : '最新可用数据'} · {history?.count ?? 0} 个数据点
          </span>
        }
      >
        <KlineChart
          data={(history?.items ?? []).map((i) => ({ date: i.date, value: i.nav, volume: i.volume }))}
          loading={!history}
          name="净值"
          period={period}
          height={460}
        />
      </Card>

      <Card title="与基准对比">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <span className="text-xs text-zinc-500">对比基准：</span>
          <Segmented
            value={benchmark}
            onChange={setBenchmark}
            options={(indexes.data ?? []).slice(0, 10).map((i) => ({ value: i.index_code, label: i.index_name }))}
          />
          {indexes.loading && <Skeleton className="h-6 w-40" />}
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {(
            [
              ['基金区间收益', formatPct(fundReturn), pctColor(fundReturn)],
              ['基准区间收益', formatPct(benchReturn), pctColor(benchReturn)],
              ['超额收益', formatPct(excess), pctColor(excess)],
              ['Beta', formatNum(metrics?.beta, 2), 'text-zinc-200'],
              ['Alpha', formatPct(metrics?.alpha), metrics?.alpha !== null && metrics?.alpha !== undefined && metrics.alpha > 0 ? 'text-up' : 'text-zinc-200'],
            ] as [string, string, string][]
          ).map(([label, value, color]) => (
            <div key={label} className="rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5">
              <div className="text-[10px] text-zinc-500">{label}</div>
              <div className={cn('num-mono mt-1 text-sm font-semibold', color)}>{value}</div>
            </div>
          ))}
        </div>
        <NavChart
          series={[
            {
              name: (history?.fund.fund_name ?? code) + '（归一化）',
              data: navSeries,
              color: ACCENT,
              area: true,
            },
            {
              name: (benchHistory.data?.index?.index_name ?? '基准') + '（归一化）',
              data: benchSeries,
              color: '#8b93a7',
              dashed: true,
            },
          ]}
          normalize
          percent
          height={300}
          loading={!history}
        />
        <p className="mt-2 text-[11px] text-zinc-600">
          超额收益 = 基金区间收益 − 基准区间收益；Beta / Alpha 来自 /funds/{code}/risk（默认区间）。
        </p>
      </Card>
    </div>
  );
}

// ---------- Tab: 技术指标 ----------
const INDICATOR_LABELS: [string, string][] = [
  ['ma5', 'MA5'],
  ['ma10', 'MA10'],
  ['ma20', 'MA20'],
  ['ma60', 'MA60'],
  ['ema12', 'EMA12'],
  ['ema26', 'EMA26'],
  ['macd', 'MACD'],
  ['macd_signal', 'MACD 信号'],
  ['macd_hist', 'MACD 柱'],
  ['rsi14', 'RSI(14)'],
  ['bb_upper', '布林上轨'],
  ['bb_mid', '布林中轨'],
  ['bb_lower', '布林下轨'],
  ['atr14', 'ATR(14)'],
  ['momentum_5d', '5日动量'],
  ['momentum_20d', '20日动量'],
  ['momentum_60d', '60日动量'],
];

function IndicatorsTab({ code }: { code: string }) {
  const ind = useApi<IndicatorsResponse>(() => api.get(`/funds/${code}/indicators`), [code]);
  const all = ind.data?.indicators ?? {};
  const entries = INDICATOR_LABELS.filter(([k]) => all[k] !== undefined && all[k] !== null);
  const extra = Object.entries(all)
    .filter(([k, v]) => v !== null && v !== undefined && !INDICATOR_LABELS.some(([lk]) => lk === k))
    .slice(0, 20);

  return (
    <Card title="技术指标" extra={ind.data?.date ? <span className="text-[11px] text-zinc-600">数据日期 {formatDate(ind.data.date)}</span> : undefined}>
      {ind.loading && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
      )}
      {ind.error && <ErrorState message={ind.error} onRetry={ind.reload} />}
      {!ind.loading && !ind.error && entries.length === 0 && (
        <EmptyState title="暂无技术指标数据" desc="/funds/{code}/indicators 未返回指标" icon="📐" />
      )}
      {!ind.loading && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-4">
          {entries.map(([key, label]) => {
            const v = all[key];
            return (
              <div key={key} className="rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5">
                <div className="text-[10px] text-zinc-500">{label}</div>
                <div className="num-mono mt-1 text-sm font-semibold text-zinc-100">
                  {v === null || v === undefined ? '--' : Number(v).toFixed(4)}
                </div>
              </div>
            );
          })}
          {extra.map(([key, v]) => (
            <div key={key} className="rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5">
              <div className="text-[10px] text-zinc-500">{key}</div>
              <div className="num-mono mt-1 text-sm font-semibold text-zinc-100">
                {v === null || v === undefined ? '--' : Number(v).toFixed(4)}
              </div>
            </div>
          ))}
        </div>
      )}
      {ind.data?.computed_at && (
        <div className="mt-3 text-[11px] text-zinc-600">计算时间：{formatDateTime(ind.data.computed_at)}</div>
      )}
    </Card>
  );
}

// ---------- Tab: 风险指标 ----------
function RiskTab({ code, history }: { code: string; history: NavHistoryResponse | null }) {
  const risk = useApi<RiskResponse>(() => api.get(`/funds/${code}/risk`), [code]);
  const drawdownSeries = useMemo(() => {
    const navs = (history?.items ?? [])
      .map((i) => i.nav)
      .filter((v): v is number => v !== null && v !== undefined);
    let peak = -Infinity;
    const out: [string, number][] = [];
    (history?.items ?? []).forEach((i, idx) => {
      const v = navs[idx];
      if (v === undefined) return;
      if (v > peak) peak = v;
      const dd = peak > 0 ? ((v - peak) / peak) * 100 : 0;
      out.push([i.date, Number(dd.toFixed(2))]);
    });
    return out;
  }, [history]);

  const m = risk.data?.metrics;
  const cards: [string, string, string][] = [
    ['年化收益', m?.annual_return !== null && m?.annual_return !== undefined ? `${m.annual_return.toFixed(2)}%` : '--', 'text-zinc-100'],
    ['年化波动率', m?.annual_volatility !== null && m?.annual_volatility !== undefined ? `${m.annual_volatility.toFixed(2)}%` : '--', 'text-zinc-100'],
    ['下行波动率', m?.downside_volatility !== null && m?.downside_volatility !== undefined ? `${m.downside_volatility.toFixed(2)}%` : '--', 'text-zinc-100'],
    ['最大回撤', m?.max_drawdown !== null && m?.max_drawdown !== undefined ? `${m.max_drawdown.toFixed(2)}%` : '--', 'text-down'],
    ['Sharpe', formatNum(m?.sharpe, 2), (m?.sharpe ?? 0) > 0 ? 'text-up' : 'text-zinc-100'],
    ['Sortino', formatNum(m?.sortino, 2), (m?.sortino ?? 0) > 0 ? 'text-up' : 'text-zinc-100'],
    ['Calmar', formatNum(m?.calmar, 2), (m?.calmar ?? 0) > 0 ? 'text-up' : 'text-zinc-100'],
    ['VaR(95%)', m?.var_95 !== null && m?.var_95 !== undefined ? `${m.var_95.toFixed(2)}%` : '--', 'text-zinc-100'],
    ['CVaR(95%)', m?.cvar_95 !== null && m?.cvar_95 !== undefined ? `${m.cvar_95.toFixed(2)}%` : '--', 'text-zinc-100'],
    ['Beta', formatNum(m?.beta, 2), 'text-zinc-100'],
    ['Alpha', m?.alpha !== null && m?.alpha !== undefined ? `${m.alpha.toFixed(2)}%` : '--', (m?.alpha ?? 0) > 0 ? 'text-up' : 'text-zinc-100'],
    ['信息比率', formatNum(m?.information_ratio, 2), (m?.information_ratio ?? 0) > 0 ? 'text-up' : 'text-zinc-100'],
    ['最佳单日', m?.best_day !== null && m?.best_day !== undefined ? `${m.best_day.toFixed(2)}%` : '--', 'text-up'],
    ['最差单日', m?.worst_day !== null && m?.worst_day !== undefined ? `${m.worst_day.toFixed(2)}%` : '--', 'text-down'],
  ];

  return (
    <div className="space-y-4">
      <Card title="风险指标" extra={risk.data?.period ? <span className="text-[11px] text-zinc-600">区间 {risk.data.period}</span> : undefined}>
        {risk.loading && (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
            {Array.from({ length: 14 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-lg" />
            ))}
          </div>
        )}
        {risk.error && <ErrorState message={risk.error} onRetry={risk.reload} />}
        {!risk.loading && !risk.error && (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
            {cards.map(([label, value, color]) => (
              <div key={label} className="rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5">
                <div className="text-[10px] text-zinc-500">{label}</div>
                <div className={cn('num-mono mt-1 text-sm font-semibold', color)}>{value}</div>
              </div>
            ))}
          </div>
        )}
        {risk.data?.computed_at && (
          <div className="mt-3 text-[11px] text-zinc-600">计算时间：{formatDateTime(risk.data.computed_at)}</div>
        )}
      </Card>

      <Card title="历史回撤曲线（%）">
        {drawdownSeries.length === 0 && <EmptyState title="暂无足够历史数据" icon="📉" />}
        {drawdownSeries.length > 0 && (
          <NavChart
            series={[
              {
                name: '回撤',
                data: drawdownSeries,
                color: '#10b981',
                area: true,
              },
            ]}
            height={260}
          />
        )}
        <p className="mt-2 text-[11px] text-zinc-600">
          最新最大回撤（近 {history?.items.length ?? 0} 个数据点）：{' '}
          <span className="num-mono text-down">{(maxDrawdown((history?.items ?? []).map((i) => i.nav ?? 0)) * 100).toFixed(2)}%</span>
        </p>
      </Card>
    </div>
  );
}

// ---------- Tab: 持仓 ----------
function HoldingsTab({ code }: { code: string }) {
  const hold = useApi<HoldingsResponse>(() => api.get(`/funds/${code}/holdings`), [code]);
  const top10 = hold.data?.top10 ?? [];
  const maxWeight = Math.max(1, ...top10.map((h) => h.weight ?? 0));
  const industries = hold.data?.industry_distribution ?? [];

  return (
    <div className="space-y-4">
      <Card
        title="前十大持仓"
        extra={hold.data?.report_date ? <span className="text-[11px] text-zinc-600">报告期 {formatDate(hold.data.report_date)}</span> : undefined}
      >
        {hold.loading && <Skeleton className="h-64 w-full" />}
        {hold.error && <ErrorState message={hold.error} onRetry={hold.reload} />}
        {!hold.loading && !hold.error && top10.length === 0 && (
          <EmptyState title="暂无持仓数据" desc="/funds/{code}/holdings 未返回 top10" icon="💼" />
        )}
        {!hold.loading && top10.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 text-[11px] text-zinc-500">
                  <th className="py-2 pr-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">股票</th>
                  <th className="px-2 py-2 font-medium">行业</th>
                  <th className="px-2 py-2 font-medium">权重</th>
                  <th className="px-2 py-2 font-medium">权重占比</th>
                  <th className="py-2 pl-2 text-right font-medium">市值（亿）</th>
                </tr>
              </thead>
              <tbody>
                {top10.map((h, i) => (
                  <tr key={h.stock_code + i} className="border-b border-white/5">
                    <td className="py-2.5 pr-2 text-xs text-zinc-500">{i + 1}</td>
                    <td className="px-2 py-2.5">
                      <div className="text-zinc-100">{h.stock_name}</div>
                      <div className="num-mono text-[10px] text-zinc-600">{h.stock_code}</div>
                    </td>
                    <td className="px-2 py-2.5 text-xs text-zinc-400">{h.industry ?? '--'}</td>
                    <td className="num-mono px-2 py-2.5 text-sm font-semibold text-zinc-100">
                      {h.weight?.toFixed(2) ?? '--'}%
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="h-2 w-28 overflow-hidden rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-red-500 to-amber-500"
                          style={{ width: `${Math.max(2, ((h.weight ?? 0) / maxWeight) * 100)}%` }}
                        />
                      </div>
                    </td>
                    <td className="num-mono py-2.5 pl-2 text-right text-xs text-zinc-400">
                      {compactCN(h.market_value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {hold.data?.concentration && (
          <div className="mt-3 flex gap-3">
            <span className="rounded-lg border border-white/5 bg-surface-2 px-3 py-1.5 text-xs text-zinc-400">
              前十大集中度：<span className="num-mono font-semibold text-zinc-100">{hold.data.concentration.top10?.toFixed(1) ?? '--'}%</span>
            </span>
            <span className="rounded-lg border border-white/5 bg-surface-2 px-3 py-1.5 text-xs text-zinc-400">
              HHI：<span className="num-mono font-semibold text-zinc-100">{hold.data.concentration.hhi?.toFixed(3) ?? '--'}</span>
            </span>
          </div>
        )}
      </Card>

      <Card title="行业分布">
        {industries.length === 0 && <EmptyState title="暂无行业分布数据" icon="🏭" />}
        {industries.length > 0 && (
          <div className="space-y-2.5">
            {industries
              .slice()
              .sort((a, b) => b.weight - a.weight)
              .map((ind) => (
                <div key={ind.industry} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 truncate text-xs text-zinc-300">{ind.industry}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400"
                      style={{ width: `${Math.max(2, Math.min(100, ind.weight))}%` }}
                    />
                  </div>
                  <span className="num-mono w-14 shrink-0 text-right text-xs text-zinc-200">
                    {ind.weight.toFixed(1)}%
                  </span>
                </div>
              ))}
          </div>
        )}
        {hold.data?.retrieved_at && (
          <div className="mt-3 text-[11px] text-zinc-600">数据获取：{formatDateTime(hold.data.retrieved_at)} · 来源 {hold.data.source}</div>
        )}
      </Card>
    </div>
  );
}

// ---------- Tab: AI 分析 ----------
const BREAKDOWN_LABELS: Record<string, string> = {
  trend: '趋势',
  volatility: '波动',
  risk: '风险',
  quality: '质量',
  macro: '宏观',
  industry: '行业',
  sentiment: '情绪',
};

function FactorList({
  title,
  items,
  tone,
}: {
  title: string;
  items: { factor: string; reason: string | null; evidence: string | null; value: number | null }[];
  tone: 'up' | 'down';
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-surface-2 p-4">
      <div className={cn('mb-3 text-sm font-semibold', tone === 'up' ? 'text-up' : 'text-down')}>
        {title}（{items.length}）
      </div>
      {items.length === 0 && <div className="text-xs text-zinc-600">暂无</div>}
      <div className="space-y-3">
        {items.map((f, i) => (
          <div key={i} className="text-xs leading-relaxed">
            <div className="flex items-center gap-2">
              <span className="font-medium text-zinc-100">{f.factor}</span>
              {f.value !== null && f.value !== undefined && (
                <span className="num-mono text-[10px] text-zinc-500">评分 {f.value}</span>
              )}
            </div>
            {f.reason && <p className="mt-0.5 text-zinc-400">{f.reason}</p>}
            {f.evidence && <p className="num-mono mt-0.5 text-[10px] text-zinc-600">证据：{f.evidence}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function AiAnalysisTab({ code }: { code: string }) {
  const analysis = useApi<FundAnalysisResponse>(() => api.get(`/funds/${code}/analysis`), [code]);
  const predShort = useApi<PredictionResponse>(() => api.get(`/funds/${code}/prediction`, { horizon: 'short' }), [code]);
  const predMedium = useApi<PredictionResponse>(() => api.get(`/funds/${code}/prediction`, { horizon: 'medium' }), [code]);
  const predLong = useApi<PredictionResponse>(() => api.get(`/funds/${code}/prediction`, { horizon: 'long' }), [code]);

  const breakdown = analysis.data?.score_breakdown ?? {};
  const radarIndicators = Object.keys(breakdown).map((k) => ({ name: BREAKDOWN_LABELS[k] ?? k, max: 100 }));
  const radarSeries = [{ name: '评分维度', data: Object.values(breakdown) }];

  const predictions: { label: string; p: PredictionResponse | null; loading: boolean }[] = [
    { label: '短期（5日）', p: predShort.data, loading: predShort.loading },
    { label: '中期（20日）', p: predMedium.data, loading: predMedium.loading },
    { label: '长期（60日）', p: predLong.data, loading: predLong.loading },
  ];

  return (
    <div className="space-y-4">
      {/* 评分 + 雷达 */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Card title="综合评分" bodyClassName="flex items-center justify-center p-2">
          {analysis.loading ? <Skeleton className="h-48 w-48 rounded-full" /> : <Gauge value={analysis.data?.score} name="AI 评分" height={210} />}
        </Card>
        <Card title="七维因子评分" className="lg:col-span-2">
          {analysis.loading ? <Skeleton className="h-56 w-full" /> : <RadarChart indicators={radarIndicators} series={radarSeries} height={260} legend={false} />}
        </Card>
      </div>

      {/* 趋势 + 市场环境 */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card title="趋势判断">
          {analysis.loading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {(
                [
                  ['短期', analysis.data?.trend?.short],
                  ['中期', analysis.data?.trend?.medium],
                  ['长期', analysis.data?.trend?.long],
                ] as [string, string | undefined][]
              ).map(([label, t]) => (
                <span key={label} className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-surface-2 px-3 py-2 text-xs text-zinc-400">
                  {label}：<TrendBadge trend={t} />
                </span>
              ))}
            </div>
          )}
        </Card>
        <Card title="市场环境">
          {analysis.loading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {(
                [
                  ['短期', analysis.data?.regime?.short],
                  ['中期', analysis.data?.regime?.medium],
                  ['长期', analysis.data?.regime?.long],
                ] as [string, string | undefined][]
              ).map(([label, t]) => (
                <span key={label} className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-surface-2 px-3 py-2 text-xs text-zinc-400">
                  {label}：<TrendBadge trend={t} />
                </span>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* 预测 */}
      <Card title="多周期预测（概率估计）">
        <div className="grid gap-3 md:grid-cols-3">
          {predictions.map(({ label, p, loading }) => (
            <div key={label} className="rounded-xl border border-white/5 bg-surface-2 p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-zinc-300">{label}</span>
                {p && <ConfidenceBadge confidence={p.confidence} />}
              </div>
              {loading ? (
                <Skeleton className="mt-3 h-24 w-full" />
              ) : !p ? (
                <EmptyState title="暂无预测" icon="🔮" />
              ) : (
                <div className="mt-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className={cn('text-lg font-bold', p.direction.includes('多') || p.direction.includes('涨') ? 'text-up' : p.direction.includes('空') || p.direction.includes('跌') ? 'text-down' : 'text-zinc-100')}>
                      {p.direction}
                    </span>
                    <span className="num-mono text-[10px] text-zinc-500">置信度 {(p.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                  {p.calibrated && p.calibration_method && p.calibration_method !== 'uncalibrated' ? (
                    <div className="mb-2 text-[10px] text-zinc-500">
                      校准：{p.calibration_method} · 原始 {p.raw_probabilities?.up.toFixed(0)}/
                      {p.raw_probabilities?.range.toFixed(0)}/{p.raw_probabilities?.down.toFixed(0)}%
                    </div>
                  ) : (
                    <div className="mb-2 text-[10px] text-amber-400/80">概率未经校准（校准样本不足）</div>
                  )}
                  {p.note && (
                    <div className="mb-2 rounded bg-amber-500/10 px-2 py-1 text-[10px] leading-relaxed text-amber-300">
                      {p.note}
                    </div>
                  )}
                  <div className="space-y-1.5">
                    {(
                      [
                        ['上涨', p.probabilities.up, 'text-up'],
                        ['震荡', p.probabilities.range, 'text-zinc-300'],
                        ['下跌', p.probabilities.down, 'text-down'],
                      ] as [string, number, string][]
                    ).map(([name, prob, color]) => (
                      <div key={name} className="flex items-center gap-2">
                        <span className="w-8 text-[10px] text-zinc-500">{name}</span>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                          <div
                            className={cn('h-full rounded-full', color === 'text-up' ? 'bg-up' : color === 'text-down' ? 'bg-down' : 'bg-zinc-500')}
                            style={{ width: `${Math.max(2, Math.min(100, prob))}%` }}
                          />
                        </div>
                        <span className="num-mono w-11 text-right text-[11px] text-zinc-300">{prob.toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                  {p.feature_importance && p.feature_importance.length > 0 && (
                    <div className="mt-2.5 border-t border-white/5 pt-2">
                      <div className="mb-1 text-[10px] text-zinc-600">关键特征</div>
                      <div className="flex flex-wrap gap-1">
                        {p.feature_importance.slice(0, 5).map((f) => (
                          <span key={f.feature} className="num-mono rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-400">
                            {f.feature} {f.importance.toFixed(2)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">
          历史回测不代表未来表现；本结果仅为概率估计，不构成投资建议。模型版本：{predShort.data?.model_version ?? '--'}
          {predShort.data?.model_name ? `（${predShort.data.model_name}）` : ''}
          ；校准方法：{predShort.data?.calibration_method ?? '--'}
        </p>
      </Card>

      {/* 正负因子 */}
      <div className="grid gap-3 lg:grid-cols-2">
        <FactorList title="积极因素" items={analysis.data?.positive_factors ?? []} tone="up" />
        <FactorList title="消极因素" items={analysis.data?.negative_factors ?? []} tone="down" />
      </div>

      {/* 主要风险 */}
      <Card title="主要风险">
        {analysis.loading && <Skeleton className="h-20 w-full" />}
        {(analysis.data?.main_risks ?? []).length === 0 && !analysis.loading && (
          <EmptyState title="暂无风险提示" icon="🛡️" />
        )}
        <div className="grid gap-2 md:grid-cols-2">
          {(analysis.data?.main_risks ?? []).map((r, i) => (
            <div key={i} className="flex items-start gap-2.5 rounded-lg border border-white/5 bg-surface-2 px-3 py-2.5">
              <SeverityBadge severity={r.severity} />
              <div>
                <div className="text-xs font-medium text-zinc-200">{r.category}</div>
                <div className="mt-0.5 text-xs leading-relaxed text-zinc-400">{r.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 数据来源 */}
      <Card title="数据来源">
        <div className="flex flex-wrap gap-2">
          {(analysis.data?.data_sources ?? []).map((s, i) => (
            <span key={i} className="rounded-lg border border-white/5 bg-surface-2 px-2.5 py-1.5 text-[11px] text-zinc-400">
              {s.name} · <span className="text-zinc-300">{s.source}</span>
              {s.retrieved_at && <span className="text-zinc-600"> · {formatDateTime(s.retrieved_at)}</span>}
            </span>
          ))}
          {(analysis.data?.data_sources ?? []).length === 0 && <span className="text-xs text-zinc-600">暂无来源信息</span>}
        </div>
        <div className="mt-2 text-[11px] text-zinc-600">
          数据状态：{analysis.data?.data_status === 'estimate' ? '盘中估值' : '最新可用数据'} · 计算时间 {formatDateTime(analysis.data?.computed_at)}
        </div>
      </Card>
    </div>
  );
}

// ---------- Tab: 新闻 ----------
function FundNewsTab({ code }: { code: string }) {
  const news = useApi<NewsItem[]>(
    () => api.get<{ items: NewsItem[] }>('/news', { related_fund: code, limit: 30 }).then((r) => r.items),
    [code],
  );
  const [detail, setDetail] = useState<NewsItem | null>(null);
  return (
    <Card title="相关新闻">
      {news.loading && <Skeleton className="h-40 w-full" />}
      {news.error && <ErrorState message={news.error} onRetry={news.reload} />}
      {!news.loading && (news.data ?? []).length === 0 && (
        <EmptyState title="暂无相关新闻" desc="后端未返回与该基金相关的新闻" icon="📰" />
      )}
      <div className="divide-y divide-white/5">
        {(news.data ?? []).map((n) => (
          <button key={n.id} onClick={() => setDetail(n)} className="block w-full px-2 py-3 text-left transition hover:bg-white/[0.03]">
            <div className="text-sm text-zinc-100">{n.title}</div>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-600">
              <span>{n.source ?? '--'}</span>
              <span>{formatDateTime(n.published_at)}</span>
              {n.related_industry && <span>行业：{n.related_industry}</span>}
            </div>
          </button>
        ))}
      </div>
      {detail && (
        <Modal open onClose={() => setDetail(null)} title={detail.title} width="max-w-2xl">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] text-zinc-500">
              <span>{detail.source ?? '--'}</span>
              <span>{formatDateTime(detail.published_at)}</span>
              {detail.url && (
                <a href={detail.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  原文链接
                </a>
              )}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
              {detail.content ?? '（无正文）'}
            </p>
          </div>
        </Modal>
      )}
    </Card>
  );
}

// ---------- Tab: 政策 ----------
function FundPolicyTab() {
  const policies = useApi<PolicyItem[]>(
    () => api.get<{ items: PolicyItem[] }>('/policies', { limit: 20 }).then((r) => r.items),
    [],
  );
  const [detail, setDetail] = useState<PolicyItem | null>(null);
  return (
    <Card title="相关政策" extra={<span className="text-[11px] text-zinc-600">按影响力排序，可能与基金行业相关</span>}>
      {policies.loading && <Skeleton className="h-40 w-full" />}
      {policies.error && <ErrorState message={policies.error} onRetry={policies.reload} />}
      {!policies.loading && (policies.data ?? []).length === 0 && (
        <EmptyState title="暂无政策数据" icon="🏛️" />
      )}
      <div className="divide-y divide-white/5">
        {(policies.data ?? [])
          .slice()
          .sort((a, b) => (b.impact_score ?? 0) - (a.impact_score ?? 0))
          .map((p) => (
            <button key={p.id} onClick={() => setDetail(p)} className="block w-full px-2 py-3 text-left transition hover:bg-white/[0.03]">
              <div className="text-sm text-zinc-100">{p.title}</div>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-600">
                <span>{p.department ?? '--'}</span>
                <span>{p.policy_type ?? '--'}</span>
                <span>{formatDate(p.published_at)}</span>
              </div>
            </button>
          ))}
      </div>
      {detail && (
        <Modal open onClose={() => setDetail(null)} title={detail.title} width="max-w-2xl">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-[11px] text-zinc-500">
              <span>{detail.department ?? '--'}</span>
              <span>{detail.policy_type ?? '--'}</span>
              <span>{formatDateTime(detail.published_at)}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
              {detail.content ?? '（无正文）'}
            </p>
          </div>
        </Modal>
      )}
    </Card>
  );
}

// ---------- Tab: 预测历史（Prediction Ledger） ----------
const HORIZON_LABELS: Record<string, string> = { short: '短期', medium: '中期', long: '长期' };
const CLASS_LABELS: Record<string, string> = { up: '看涨', range: '中性', down: '看跌' };

function PredictionHistoryTab({ code }: { code: string }) {
  const ledger = useApi<LedgerResponse>(
    () => api.get<LedgerResponse>(`/prediction/ledger`, { fund_code: code, limit: 100 }),
    [code],
  );
  const records = ledger.data?.records ?? [];
  const stats = ledger.data?.stats?.overall;
  return (
    <Card
      title="预测历史（Prediction Ledger）"
      extra={
        stats && (
          <span className="num-mono text-[11px] text-zinc-500">
            近30次命中 {stats.last_30?.hit_rate != null ? `${stats.last_30.hit_rate.toFixed(1)}%` : '—'} · 近100次{' '}
            {stats.last_100?.hit_rate != null ? `${stats.last_100.hit_rate.toFixed(1)}%` : '—'}
          </span>
        )
      }
      bodyClassName="p-0"
    >
      {ledger.loading && <Skeleton className="m-2 h-40" />}
      {ledger.error && <ErrorState message={ledger.error} onRetry={ledger.reload} />}
      {!ledger.loading && records.length === 0 && (
        <EmptyState
          title="暂无预测历史"
          desc="在「AI分析」页生成预测后，此处展示每次预测与实际结果的对照；未来数据到位后自动评价命中情况。"
          icon="🗂️"
        />
      )}
      {records.length > 0 && (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/5 text-[11px] text-zinc-500">
              <th className="px-3 py-2">预测日期</th>
              <th className="px-3 py-2">周期</th>
              <th className="px-3 py-2">预测</th>
              <th className="px-3 py-2">校准概率</th>
              <th className="px-3 py-2">置信度</th>
              <th className="px-3 py-2">模型</th>
              <th className="px-3 py-2">实际结果</th>
              <th className="px-3 py-2">命中</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => {
              const prob = r.calibrated_probabilities ?? r.raw_probabilities;
              const hit = r.actual_class !== null && r.actual_class !== undefined;
              const isHit = hit && r.predicted_class === r.actual_class;
              const clsColor =
                r.predicted_class === 'up' ? 'text-up' : r.predicted_class === 'down' ? 'text-down' : 'text-zinc-300';
              return (
                <tr key={r.id} className="border-b border-white/5 last:border-0">
                  <td className="num-mono px-3 py-2 text-zinc-400">{formatDate(r.prediction_date)}</td>
                  <td className="px-3 py-2 text-zinc-400">
                    {HORIZON_LABELS[r.horizon] ?? r.horizon}（{r.horizon_days}日）
                  </td>
                  <td className={cn('px-3 py-2 font-medium', clsColor)}>
                    {CLASS_LABELS[r.predicted_class ?? ''] ?? '—'}
                  </td>
                  <td className="num-mono px-3 py-2 text-zinc-300">
                    {prob ? `↑${prob.up.toFixed(0)}/→${prob.range.toFixed(0)}/↓${prob.down.toFixed(0)}` : '—'}
                  </td>
                  <td className="px-3 py-2 text-zinc-400">{r.confidence ?? '—'}</td>
                  <td className="num-mono px-3 py-2 text-zinc-500">
                    {r.model_version ?? '—'}
                    {r.calibrated ? '' : '（未校准）'}
                  </td>
                  <td className="px-3 py-2 text-zinc-300">
                    {hit ? (
                      <>
                        <span
                          className={cn(
                            'font-medium',
                            r.actual_class === 'up' ? 'text-up' : r.actual_class === 'down' ? 'text-down' : 'text-zinc-300',
                          )}
                        >
                          {CLASS_LABELS[r.actual_class ?? ''] ?? '—'}
                        </span>
                        <span className="num-mono ml-1 text-[10px] text-zinc-500">
                          {r.actual_return != null ? `（${r.actual_return > 0 ? '+' : ''}${r.actual_return.toFixed(2)}%）` : ''}
                        </span>
                      </>
                    ) : (
                      <span className="text-zinc-600">等待评价</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {!hit ? <span className="text-zinc-700">—</span> : isHit ? <span className="text-down">✓</span> : <span className="text-up">✗</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

// ---------- 主页面 ----------
export default function FundDetail() {
  const { code = '' } = useParams();
  const navigate = useNavigate();
  const [range, setRange] = useState<RangeKey>('6M');
  const [period, setPeriod] = useState<KlinePeriod>('daily');
  const [tab, setTab] = useState<TabKey>('走势图');
  const [syncing, setSyncing] = useState(false);

  const detail = useApi<FundDetail>(() => api.get(`/funds/${code}`), [code]);

  const rangeDates = useMemo(() => {
    const end = new Date();
    let start: Date | null = null;
    if (range !== 'ALL') {
      start = new Date(end);
      start.setDate(start.getDate() - RANGE_DAYS[range]);
    }
    return { start: start ? fmtDate(start) : undefined, end: fmtDate(end) };
  }, [range]);

  const history = useApi<NavHistoryResponse>(
    () =>
      api.get(`/funds/${code}/history`, {
        start: rangeDates.start,
        end: rangeDates.end,
        period,
      }),
    [code, range, period],
  );

  const sync = async () => {
    setSyncing(true);
    try {
      const res = await api.post<{ task_id: string; status: string }>(`/funds/${code}/sync`);
      toast(`已提交数据同步任务（${res.task_id}），稍后自动刷新`, 'success');
      window.setTimeout(() => {
        detail.reload();
        history.reload();
      }, 1500);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '同步失败', 'error');
    } finally {
      setSyncing(false);
    }
  };

  const f = detail.data;
  const chip: FundChip = { code, name: f?.fund_name ?? code };

  return (
    <div className="space-y-4">
      {/* 头部 */}
      {detail.loading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-6 w-1/3" />
        </div>
      ) : detail.error ? (
        <ErrorState message={detail.error} onRetry={detail.reload} />
      ) : f ? (
        <div className="card p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-bold text-zinc-50">{f.fund_name}</h1>
                <ScoreBadge score={f.ai_score ?? f.score} />
                <DataStatusBadge status={f.data_status} />
                <RiskLevelBadge level={f.risk_level} />
              </div>
              <div className="num-mono mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                <span>{f.fund_code}</span>
                <span>{f.fund_type}</span>
                <span>{f.company ?? '--'}</span>
                {f.manager && <span>经理：{f.manager}</span>}
                {f.benchmark && <span>基准：{f.benchmark}</span>}
                {f.fund_size !== null && f.fund_size !== undefined && (
                  <span>规模：{compactCN(f.fund_size * 1e8)}</span>
                )}
                {f.establish_date && <span>成立：{formatDate(f.establish_date)}</span>}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {f.fees && (
                  <span className="rounded border border-white/10 bg-surface-2 px-2 py-0.5 text-[11px] text-zinc-400">
                    管理费 {f.fees.management_fee}% · 申购 {f.fees.purchase_fee}% · 赎回 {f.fees.redemption_fee}%
                  </span>
                )}
                <span className="text-[11px] text-zinc-600">
                  数据时间 {f.data_time ?? formatDate(f.latest_nav_date)} · 来源 {f.source}
                </span>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <div className="text-right">
                <div className="num-mono text-3xl font-bold text-zinc-50">
                  {f.latest_nav !== null && f.latest_nav !== undefined ? f.latest_nav.toFixed(4) : '--'}
                </div>
                <div className={cn('num-mono mt-1 text-sm font-medium', pctColor(f.return_1d))}>
                  {formatPct(f.return_1d)}（今日）
                </div>
                {f.estimate_nav !== null && f.estimate_nav !== undefined && f.data_status === 'estimate' && (
                  <div className="num-mono mt-0.5 text-[11px] text-amber-400">
                    估值 {f.estimate_nav.toFixed(4)}（{formatPct(f.estimate_return)}）
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Segmented<RangeKey>
                  value={range}
                  onChange={setRange}
                  options={[
                    { value: '1M', label: '1月' },
                    { value: '3M', label: '3月' },
                    { value: '6M', label: '6月' },
                    { value: '1Y', label: '1年' },
                    { value: '3Y', label: '3年' },
                    { value: 'ALL', label: '全部' },
                  ]}
                />
                <button
                  onClick={() => void sync()}
                  disabled={syncing}
                  className="inline-flex items-center justify-center gap-1.5 rounded-md border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition hover:bg-accent/20 disabled:opacity-50"
                >
                  <IconRefresh size={13} className={syncing ? 'animate-spin' : ''} />
                  {syncing ? '提交中…' : '立即更新数据'}
                </button>
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-4 border-t border-white/5 pt-3">
            {(
              [
                ['1日', f.return_1d],
                ['5日', f.return_5d],
                ['20日', f.return_20d],
                ['60日', f.return_60d],
                ['1年', f.return_1y],
                ['年初至今', f.return_ytd],
              ] as [string, number | null][]
            ).map(([label, v]) => (
              <div key={label}>
                <div className="text-[10px] text-zinc-600">{label}</div>
                <div className={cn('num-mono text-sm font-semibold', pctColor(v))}>{formatPct(v)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Tab 栏 */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/5 pb-px">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'whitespace-nowrap border-b-2 px-3.5 py-2 text-sm transition',
              tab === t
                ? 'border-accent font-medium text-accent'
                : 'border-transparent text-zinc-500 hover:text-zinc-200',
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div className="min-h-64">
        {tab === '走势图' && <TrendTab code={code} history={history.data} period={period} />}
        {tab === '技术指标' && <IndicatorsTab code={code} />}
        {tab === '风险指标' && <RiskTab code={code} history={history.data} />}
        {tab === '持仓' && <HoldingsTab code={code} />}
        {tab === 'AI分析' && <AiAnalysisTab code={code} />}
        {tab === '预测历史' && <PredictionHistoryTab code={code} />}
        {tab === '新闻' && <FundNewsTab code={code} />}
        {tab === '政策' && <FundPolicyTab />}
        {tab === 'AI对话' && (
          <Card title="AI 对话（已关联本基金）" bodyClassName="p-0">
            <div style={{ height: 520 }}>
              <ChatThread funds={[chip]} embedded height="100%" />
            </div>
          </Card>
        )}
      </div>

      <div className="text-center text-[11px] text-zinc-700">
        <button onClick={() => navigate('/funds')} className="text-accent hover:underline">
          ← 返回基金列表
        </button>
      </div>
    </div>
  );
}
