import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type {
  DailySummary,
  MarketOverview,
  NewsItem,
  NavHistoryResponse,
  PolicyItem,
  WatchlistItem,
} from '../types/api';
import { useAppStore } from '../store/app';
import { cn, compactCN, formatPct, formatDate, formatDateTime, pctColor } from '../utils/format';
import { annualVolatility, maxDrawdown, momentum, rangeReturn } from '../utils/indicators';
import { useApi } from '../utils/hooks';
import { Card, EmptyState, ErrorState, Skeleton, SkeletonCard } from '../components/ui';
import { ScoreBadge, TrendBadge, Badge } from '../components/badges';
import Sparkline from '../components/Sparkline';
import Markdown from '../components/Markdown';

function IndexStrip() {
  const overview = useApi<MarketOverview>(() => api.get('/market/overview'), []);
  if (overview.loading) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
    );
  }
  const indices = overview.data?.indices ?? [];
  if (indices.length === 0) {
    return <EmptyState title="暂无指数行情" desc="后端市场数据不可用" icon="📊" />;
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
      {indices.map((idx) => (
        <Link
          key={idx.index_code}
          to={`/market?index=${idx.index_code}`}
          className="card group p-3 transition hover:border-white/15"
        >
          <div className="truncate text-xs text-zinc-400 group-hover:text-zinc-200">
            {idx.index_name}
          </div>
          <div className="num-mono mt-1.5 text-lg font-semibold text-zinc-100">
            {idx.latest_close !== null && idx.latest_close !== undefined
              ? idx.latest_close.toFixed(2)
              : '--'}
          </div>
          <div className={cn('num-mono mt-0.5 text-xs font-medium', pctColor(idx.change_pct))}>
            {formatPct(idx.change_pct)}
          </div>
        </Link>
      ))}
    </div>
  );
}

function RegimeCard({ overview }: { overview: MarketOverview | null }) {
  const regime = overview?.market_regime;
  if (!regime) {
    return <EmptyState title="暂无市场环境判断" desc="market/overview 未返回 market_regime" icon="🧭" />;
  }
  const score = regime.score ?? 0;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-zinc-100">{regime.label}</div>
          <div className="mt-0.5 text-[11px] text-zinc-500">市场环境评分</div>
        </div>
        <div className="num-mono text-2xl font-bold text-accent">{Math.round(score)}</div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-red-500"
          style={{ width: `${Math.min(100, Math.max(2, score))}%` }}
        />
      </div>
      <div>
        <div className="mb-1.5 text-[11px] text-zinc-500">核心驱动因素</div>
        <ul className="space-y-1">
          {(regime.drivers ?? []).map((d, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs text-zinc-300">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
              {d}
            </li>
          ))}
          {(regime.drivers ?? []).length === 0 && (
            <li className="text-xs text-zinc-600">暂无驱动因素说明</li>
          )}
        </ul>
      </div>
      {overview?.generated_at && (
        <div className="text-[10px] text-zinc-600">生成时间：{formatDateTime(overview.generated_at)}</div>
      )}
    </div>
  );
}

function AiSummaryCard() {
  const summary = useApi<DailySummary>(() => api.get('/summary/daily'), []);
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-accent/15 text-[11px] text-accent">
            AI
          </span>
          今日市场 AI 总结
        </span>
      }
      extra={
        summary.data?.fallback ? (
          <Badge tone="amber">量化引擎摘要（LLM 不可用）</Badge>
        ) : undefined
      }
      bodyClassName="p-5"
    >
      {summary.loading && (
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}
      {summary.error && <ErrorState message={summary.error} onRetry={summary.reload} />}
      {!summary.loading && !summary.error && !summary.data?.text && (
        <EmptyState title="暂无 AI 总结" desc="/summary/daily 未返回内容" icon="🤖" />
      )}
      {!summary.loading && summary.data?.text && (
        <div>
          <Markdown content={summary.data.text} />
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(summary.data.drivers ?? []).map((d, i) => (
              <span
                key={i}
                className="rounded-full border border-white/10 bg-surface-2 px-2 py-0.5 text-[11px] text-zinc-400"
              >
                {d}
              </span>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-zinc-600">
            生成时间：{formatDateTime(summary.data.generated_at)}
          </div>
        </div>
      )}
    </Card>
  );
}

function WatchlistGrid() {
  const navigate = useNavigate();
  const watchlistVersion = useAppStore((s) => s.watchlistVersion);
  const watchlist = useApi<WatchlistItem[]>(() => api.get('/watchlist'), [watchlistVersion]);
  const [histories, setHistories] = useState<Record<string, number[]>>({});
  const [histLoading, setHistLoading] = useState(false);

  useEffect(() => {
    const items = (watchlist.data ?? []).slice(0, 8);
    if (items.length === 0) {
      setHistories({});
      return;
    }
    let alive = true;
    setHistLoading(true);
    Promise.all(
      items.map((w) =>
        api
          .get<NavHistoryResponse>(`/funds/${w.fund.fund_code}/history`, { period: 'daily' })
          .then((r) => ({
            code: w.fund.fund_code,
            navs: r.items
              .map((i) => i.nav)
              .filter((v): v is number => v !== null && v !== undefined),
          }))
          .catch(() => ({ code: w.fund.fund_code, navs: [] as number[] })),
      ),
    )
      .then((results) => {
        if (!alive) return;
        const map: Record<string, number[]> = {};
        results.forEach((r) => {
          map[r.code] = r.navs;
        });
        setHistories(map);
      })
      .finally(() => {
        if (alive) setHistLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [watchlist.data]);

  if (watchlist.loading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }
  const items = watchlist.data ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="自选列表为空"
        desc="去「基金」页搜索并加入自选基金，仪表盘将展示实时概览"
        icon="⭐"
        action={
          <Link
            to="/funds"
            className="rounded-md bg-accent px-3 py-1.5 text-xs text-white transition hover:bg-blue-600"
          >
            去添加自选
          </Link>
        }
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((w) => {
        const f = w.fund;
        const navs = histories[f.fund_code] ?? [];
        return (
          <button
            key={w.id}
            onClick={() => navigate(`/funds/${f.fund_code}`)}
            className="card group p-4 text-left transition hover:border-accent/40"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-zinc-100 group-hover:text-accent">
                  {f.fund_name}
                </div>
                <div className="num-mono mt-0.5 text-[11px] text-zinc-500">
                  {f.fund_code} · {f.fund_type}
                </div>
              </div>
              <ScoreBadge score={f.score} />
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="num-mono text-2xl font-bold text-zinc-50">
                {f.latest_nav !== null && f.latest_nav !== undefined ? f.latest_nav.toFixed(4) : '--'}
              </span>
              <span className={cn('num-mono text-xs font-medium', pctColor(f.return_1d))}>
                {formatPct(f.return_1d)}
              </span>
            </div>
            <div className="mt-1 text-[10px] text-zinc-600">净值日期 {formatDate(f.latest_nav_date)}</div>
            <div className="mt-2 h-9">
              {histLoading && navs.length === 0 ? (
                <Skeleton className="h-full w-full" />
              ) : (
                <Sparkline data={navs.slice(-40)} trendColor height={36} />
              )}
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1 border-t border-white/5 pt-2 text-center">
              {(
                [
                  ['1日', f.return_1d],
                  ['5日', f.return_5d],
                  ['20日', f.return_20d],
                ] as [string, number | null][]
              ).map(([label, v]) => (
                <div key={label}>
                  <div className="text-[10px] text-zinc-600">{label}</div>
                  <div className={cn('num-mono text-xs font-medium', pctColor(v))}>{formatPct(v)}</div>
                </div>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function RankingCards({ watchlist }: { watchlist: WatchlistItem[] }) {
  const [histories, setHistories] = useState<Record<string, number[]>>({});
  useEffect(() => {
    if (watchlist.length === 0) return;
    let alive = true;
    Promise.all(
      watchlist.map((w) =>
        api
          .get<NavHistoryResponse>(`/funds/${w.fund.fund_code}/history`, { period: 'daily' })
          .then((r) => ({
            code: w.fund.fund_code,
            navs: r.items
              .map((i) => i.nav)
              .filter((v): v is number => v !== null && v !== undefined),
          }))
          .catch(() => ({ code: w.fund.fund_code, navs: [] as number[] })),
      ),
    ).then((results) => {
      if (!alive) return;
      const map: Record<string, number[]> = {};
      results.forEach((r) => {
        map[r.code] = r.navs;
      });
      setHistories(map);
    });
    return () => {
      alive = false;
    };
  }, [watchlist]);

  const { risk, trend } = useMemo(() => {
    const withData = watchlist
      .map((w) => ({
        code: w.fund.fund_code,
        name: w.fund.fund_name,
        navs: histories[w.fund.fund_code] ?? [],
      }))
      .filter((x) => x.navs.length >= 20);
    const risk = withData
      .map((x) => ({
        code: x.code,
        name: x.name,
        vol: annualVolatility(x.navs),
        mdd: maxDrawdown(x.navs),
      }))
      .sort((a, b) => b.mdd - a.mdd)
      .slice(0, 5);
    const trend = withData
      .map((x) => ({
        code: x.code,
        name: x.name,
        mom: momentum(x.navs, 20),
        ret60: rangeReturn(x.navs, 60),
      }))
      .sort((a, b) => b.mom - a.mom)
      .slice(0, 5);
    return { risk, trend };
  }, [watchlist, histories]);

  const renderRow = (
    row: { code: string; name: string },
    primary: string,
    primaryColor: string,
    secondary: string,
    secondaryColor: string,
  ) => (
    <Link
      key={row.code}
      to={`/funds/${row.code}`}
      className="flex items-center justify-between rounded-lg px-2 py-1.5 transition hover:bg-white/5"
    >
      <div className="min-w-0">
        <div className="truncate text-xs text-zinc-200">{row.name}</div>
        <div className="num-mono text-[10px] text-zinc-600">{row.code}</div>
      </div>
      <div className="flex items-center gap-3">
        <span className={cn('num-mono text-xs font-medium', primaryColor)}>{primary}</span>
        <span className={cn('num-mono w-14 text-right text-[11px]', secondaryColor)}>
          {secondary}
        </span>
      </div>
    </Link>
  );

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card title="风险排行（最大回撤）" bodyClassName="p-2">
        {risk.length === 0 && <EmptyState title="暂无足够历史数据" icon="🛡️" />}
        <div className="space-y-0.5">
          {risk.map((r) =>
            renderRow(r, formatPct(-r.mdd * 100), 'text-down', `波动 ${r.vol.toFixed(1)}%`, 'text-zinc-400'),
          )}
        </div>
      </Card>
      <Card title="趋势排行（20日动量）" bodyClassName="p-2">
        {trend.length === 0 && <EmptyState title="暂无足够历史数据" icon="🚀" />}
        <div className="space-y-0.5">
          {trend.map((r) =>
            renderRow(r, formatPct(r.mom), pctColor(r.mom), `60日 ${formatPct(r.ret60)}`, 'text-zinc-400'),
          )}
        </div>
      </Card>
    </div>
  );
}

function NewsPolicyRows() {
  const news = useApi<NewsItem[]>(
    () => api.get<{ items: NewsItem[] }>('/news', { limit: 50 }).then((r) => r.items),
    [],
  );
  const policies = useApi<PolicyItem[]>(
    () => api.get<{ items: PolicyItem[] }>('/policies', { limit: 50 }).then((r) => r.items),
    [],
  );

  const topNews = useMemo(
    () =>
      (news.data ?? [])
        .slice()
        .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0))
        .slice(0, 5),
    [news.data],
  );
  const topPolicies = useMemo(
    () =>
      (policies.data ?? [])
        .slice()
        .sort((a, b) => (b.impact_score ?? 0) - (a.impact_score ?? 0))
        .slice(0, 5),
    [policies.data],
  );

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card title="重要新闻" extra={<Link to="/news" className="text-xs text-accent hover:text-blue-300">更多 ›</Link>} bodyClassName="p-2">
        {news.loading && <Skeleton className="mx-2 h-24" />}
        {!news.loading && topNews.length === 0 && <EmptyState title="暂无新闻" icon="📰" />}
        <div className="space-y-0.5">
          {topNews.map((n) => (
            <Link
              key={n.id}
              to={`/news?focus=${n.id}`}
              className="block rounded-lg px-2 py-2 transition hover:bg-white/5"
            >
              <div className="line-clamp-1 text-xs text-zinc-200">{n.title}</div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-zinc-600">
                <span>{n.source ?? '未知来源'}</span>
                {n.related_industry && <span>{n.related_industry}</span>}
                {n.published_at && <span>{formatDate(n.published_at)}</span>}
              </div>
            </Link>
          ))}
        </div>
      </Card>
      <Card title="政策影响" extra={<Link to="/policy" className="text-xs text-accent hover:text-blue-300">更多 ›</Link>} bodyClassName="p-2">
        {policies.loading && <Skeleton className="mx-2 h-24" />}
        {!policies.loading && topPolicies.length === 0 && <EmptyState title="暂无政策" icon="🏛️" />}
        <div className="space-y-0.5">
          {topPolicies.map((p) => (
            <Link
              key={p.id}
              to={`/policy?focus=${p.id}`}
              className="block rounded-lg px-2 py-2 transition hover:bg-white/5"
            >
              <div className="line-clamp-1 text-xs text-zinc-200">{p.title}</div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-zinc-600">
                <span>{p.department ?? '未知部门'}</span>
                {p.related_industry && <span>{p.related_industry}</span>}
                {p.published_at && <span>{formatDate(p.published_at)}</span>}
              </div>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}

export default function Dashboard() {
  const watchlistVersion = useAppStore((s) => s.watchlistVersion);
  const watchlist = useApi<WatchlistItem[]>(() => api.get('/watchlist'), [watchlistVersion]);
  const overview = useApi<MarketOverview>(() => api.get('/market/overview'), []);

  return (
    <div className="space-y-4">
      <IndexStrip />

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AiSummaryCard />
        </div>
        <Card title="市场环境">
          {overview.loading && <Skeleton className="h-40 w-full" />}
          {!overview.loading && <RegimeCard overview={overview.data} />}
        </Card>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200">我的自选</h2>
          <Link to="/funds" className="text-xs text-accent hover:text-blue-300">
            管理自选 ›
          </Link>
        </div>
        <WatchlistGrid />
      </div>

      <RankingCards watchlist={watchlist.data ?? []} />

      <NewsPolicyRows />
    </div>
  );
}
