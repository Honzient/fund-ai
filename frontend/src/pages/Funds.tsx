import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { FundSummary, WatchlistItem } from '../types/api';
import { useAppStore } from '../store/app';
import { toast } from '../store/toast';
import { cn, formatDate, formatPct, pctColor } from '../utils/format';
import { useApi, useDebounce } from '../utils/hooks';
import { Button, Input, Select } from '../components/controls';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, Spinner } from '../components/ui';
import { DataStatusBadge, RiskLevelBadge, ScoreBadge } from '../components/badges';
import { IconPin, IconPlus, IconSearch, IconTrash } from '../components/icons';

const GROUPS_SEED = ['默认', '核心基金', '科技'];

export default function Funds() {
  const navigate = useNavigate();
  const watchlistVersion = useAppStore((s) => s.watchlistVersion);
  const bumpWatchlist = useAppStore((s) => s.bumpWatchlist);

  // ---------- 搜索 ----------
  const [search, setSearch] = useState('');
  const [fundType, setFundType] = useState('');
  const debouncedSearch = useDebounce(search, 350);
  const [searched, setSearched] = useState(false);
  const searchApi = useApi<FundSummary[]>(
    () => api.get('/funds', { search: debouncedSearch || undefined, fund_type: fundType || undefined }),
    [debouncedSearch, fundType],
  );

  // ---------- 自选 ----------
  const [groups, setGroups] = useState<string[]>(GROUPS_SEED);
  const [activeGroup, setActiveGroup] = useState('全部');
  const watchlist = useApi<WatchlistItem[]>(() => api.get('/watchlist'), [watchlistVersion]);
  const [newGroupName, setNewGroupName] = useState('');
  const [addTarget, setAddTarget] = useState<FundSummary | null>(null);
  const [addGroupName, setAddGroupName] = useState('默认');

  // 同步后端分组
  useEffect(() => {
    api
      .get<string[]>('/watchlist/groups')
      .then((list) => {
        if (Array.isArray(list) && list.length > 0) {
          setGroups((g) => Array.from(new Set([...GROUPS_SEED, ...list])));
        }
      })
      .catch(() => {
        /* 后端不可用时用种子分组 */
      });
  }, [watchlistVersion]);

  const filteredWatchlist = useMemo(() => {
    const items = watchlist.data ?? [];
    if (activeGroup === '全部') return items;
    return items.filter((w) => w.group_name === activeGroup);
  }, [watchlist.data, activeGroup]);

  // ---------- 操作 ----------
  const addToWatchlist = async (fund: FundSummary, group: string) => {
    try {
      await api.post('/watchlist', { fund_code: fund.fund_code, group_name: group });
      toast(`已将「${fund.fund_name}」加入自选（${group}）`, 'success');
      setAddTarget(null);
      bumpWatchlist();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '加入自选失败', 'error');
    }
  };

  const togglePin = async (item: WatchlistItem) => {
    try {
      await api.patch(`/watchlist/${item.id}`, { pinned: !item.pinned });
      bumpWatchlist();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '操作失败', 'error');
    }
  };

  const removeItem = async (item: WatchlistItem) => {
    try {
      await api.delete(`/watchlist/${item.id}`);
      toast('已移出自选', 'info');
      bumpWatchlist();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '删除失败', 'error');
    }
  };

  const moveGroup = async (item: WatchlistItem, group: string) => {
    if (group === item.group_name) return;
    try {
      await api.patch(`/watchlist/${item.id}`, { group_name: group });
      toast('已移动分组', 'success');
      bumpWatchlist();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : '移动分组失败', 'error');
    }
  };

  const addGroup = () => {
    const name = newGroupName.trim();
    if (!name) return;
    if (groups.includes(name)) {
      toast('分组已存在', 'error');
      return;
    }
    setGroups((g) => [...g, name]);
    setNewGroupName('');
    toast(`已创建分组「${name}」`, 'success');
  };

  const groupOptions = groups.map((g) => ({ value: g, label: g }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="基金"
        desc="搜索全市场基金并管理自选组合"
      />

      {/* 搜索区 */}
      <Card bodyClassName="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-52 flex-1">
            <IconSearch size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <Input
              value={search}
              onChange={(v) => {
                setSearch(v);
                setSearched(true);
              }}
              placeholder="输入基金名称 / 代码搜索，如：110022 或 易方达"
              className="pl-9"
            />
          </div>
          <Select
            value={fundType}
            onChange={(v) => {
              setFundType(v);
              setSearched(true);
            }}
            options={[
              { value: '', label: '全部类型' },
              { value: '股票型', label: '股票型' },
              { value: '混合型', label: '混合型' },
              { value: '指数型', label: '指数型' },
              { value: '债券型', label: '债券型' },
              { value: 'QDII', label: 'QDII' },
            ]}
          />
          <Button
            onClick={() => searchApi.reload()}
            variant="default"
            size="sm"
            disabled={!debouncedSearch && !fundType}
          >
            搜索
          </Button>
        </div>

        {/* 搜索结果 */}
        {searched && (
          <div className="mt-4">
            {searchApi.loading && (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            )}
            {searchApi.error && <ErrorState message={searchApi.error} onRetry={searchApi.reload} />}
            {!searchApi.loading && !searchApi.error && (searchApi.data ?? []).length === 0 && (
              <EmptyState title="未找到匹配基金" desc="试试其他关键词或基金代码" icon="🔍" />
            )}
            {!searchApi.loading && (searchApi.data ?? []).length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/5 text-[11px] text-zinc-500">
                      <th className="py-2 pr-3 font-medium">基金</th>
                      <th className="px-3 py-2 font-medium">类型</th>
                      <th className="px-3 py-2 text-right font-medium">最新净值</th>
                      <th className="px-3 py-2 text-right font-medium">1日</th>
                      <th className="px-3 py-2 text-right font-medium">20日</th>
                      <th className="px-3 py-2 text-right font-medium">1年</th>
                      <th className="px-3 py-2 text-center font-medium">评分</th>
                      <th className="px-3 py-2 text-center font-medium">状态</th>
                      <th className="py-2 pl-3 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(searchApi.data ?? []).map((f) => (
                      <tr key={f.fund_code} className="border-b border-white/5 transition hover:bg-white/[0.03]">
                        <td className="py-2.5 pr-3">
                          <button
                            onClick={() => navigate(`/funds/${f.fund_code}`)}
                            className="block max-w-56 truncate text-left text-zinc-100 hover:text-accent"
                          >
                            {f.fund_name}
                          </button>
                          <div className="num-mono text-[10px] text-zinc-600">
                            {f.fund_code} · {f.company ?? '--'}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-zinc-400">{f.fund_type}</td>
                        <td className="num-mono px-3 py-2.5 text-right text-zinc-100">
                          {f.latest_nav !== null && f.latest_nav !== undefined ? f.latest_nav.toFixed(4) : '--'}
                        </td>
                        <td className={cn('num-mono px-3 py-2.5 text-right', pctColor(f.return_1d))}>
                          {formatPct(f.return_1d)}
                        </td>
                        <td className={cn('num-mono px-3 py-2.5 text-right', pctColor(f.return_20d))}>
                          {formatPct(f.return_20d)}
                        </td>
                        <td className={cn('num-mono px-3 py-2.5 text-right', pctColor(f.return_1y))}>
                          {formatPct(f.return_1y)}
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <ScoreBadge score={f.score} />
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <DataStatusBadge status={f.data_status} />
                        </td>
                        <td className="py-2.5 pl-3 text-right">
                          <Button size="sm" variant="primary" onClick={() => setAddTarget(f)}>
                            <IconPlus size={13} /> 加入自选
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 自选管理 */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-zinc-200">我的自选</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setActiveGroup('全部')}
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-xs transition',
                activeGroup === '全部'
                  ? 'border-accent/50 bg-accent/15 text-accent'
                  : 'border-white/10 text-zinc-400 hover:text-zinc-200',
              )}
            >
              全部
            </button>
            {groups.map((g) => (
              <button
                key={g}
                onClick={() => setActiveGroup(g)}
                className={cn(
                  'rounded-full border px-2.5 py-0.5 text-xs transition',
                  activeGroup === g
                    ? 'border-accent/50 bg-accent/15 text-accent'
                    : 'border-white/10 text-zinc-400 hover:text-zinc-200',
                )}
              >
                {g}
              </button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <Input
              value={newGroupName}
              onChange={setNewGroupName}
              placeholder="新建分组名称"
              className="w-32 py-1 text-xs"
            />
            <Button size="sm" onClick={addGroup} disabled={!newGroupName.trim()}>
              添加分组
            </Button>
          </div>
        </div>

        <Card bodyClassName="p-2">
          {watchlist.loading && (
            <div className="space-y-2 p-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {watchlist.error && <ErrorState message={watchlist.error} onRetry={watchlist.reload} />}
          {!watchlist.loading && filteredWatchlist.length === 0 && (
            <EmptyState title="该分组暂无基金" desc="通过上方搜索结果加入自选" icon="⭐" />
          )}
          <div className="divide-y divide-white/5">
            {filteredWatchlist.map((w) => {
              const f = w.fund;
              return (
                <div key={w.id} className="flex flex-wrap items-center gap-3 px-3 py-3 transition hover:bg-white/[0.02]">
                  <button
                    onClick={() => navigate(`/funds/${f.fund_code}`)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-zinc-100 hover:text-accent">
                        {f.fund_name}
                      </span>
                      {w.pinned && <IconPin size={12} className="shrink-0 text-gold" />}
                      <ScoreBadge score={f.score} />
                      <RiskLevelBadge level={f.risk_level} />
                    </div>
                    <div className="num-mono mt-0.5 text-[11px] text-zinc-600">
                      {f.fund_code} · {f.fund_type} · 净值 {formatDate(f.latest_nav_date)}
                    </div>
                  </button>
                  <div className="flex items-center gap-4">
                    <div className="hidden text-right sm:block">
                      <div className="num-mono text-sm font-semibold text-zinc-100">
                        {f.latest_nav !== null && f.latest_nav !== undefined ? f.latest_nav.toFixed(4) : '--'}
                      </div>
                      <div className={cn('num-mono text-[11px]', pctColor(f.return_1d))}>
                        {formatPct(f.return_1d)}
                      </div>
                    </div>
                    <Select
                      value={w.group_name}
                      onChange={(g) => void moveGroup(w, g)}
                      options={groupOptions}
                      className="py-1 text-xs"
                    />
                    <button
                      onClick={() => void togglePin(w)}
                      className={cn(
                        'rounded-md p-1.5 transition',
                        w.pinned ? 'text-gold' : 'text-zinc-600 hover:text-zinc-200',
                      )}
                      title={w.pinned ? '取消置顶' : '置顶'}
                    >
                      <IconPin size={14} />
                    </button>
                    <button
                      onClick={() => void removeItem(w)}
                      className="rounded-md p-1.5 text-zinc-600 transition hover:text-red-400"
                      title="移出自选"
                    >
                      <IconTrash size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* 加入自选弹窗 */}
      {addTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setAddTarget(null)} />
          <div className="relative z-10 w-full max-w-sm rounded-xl border border-white/10 bg-surface p-5 shadow-2xl">
            <div className="text-sm font-semibold text-zinc-100">加入自选</div>
            <div className="mt-2 text-xs text-zinc-400">
              {addTarget.fund_name}（{addTarget.fund_code}）
            </div>
            <div className="mt-4">
              <div className="mb-1 text-xs text-zinc-500">选择分组</div>
              <Select value={addGroupName} onChange={setAddGroupName} options={groupOptions} className="w-full" />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setAddTarget(null)}>
                取消
              </Button>
              <Button variant="primary" size="sm" onClick={() => void addToWatchlist(addTarget, addGroupName)}>
                确认加入
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
