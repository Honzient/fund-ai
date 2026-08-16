import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { PolicyItem } from '../types/api';
import { cn, formatDateTime, timeAgo } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Select } from '../components/controls';
import { Badge, LevelBadge } from '../components/badges';
import { Modal } from '../components/overlay';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui';

export default function Policy() {
  const [params] = useSearchParams();
  const focusId = params.get('focus') ? Number(params.get('focus')) : null;
  const [department, setDepartment] = useState('');
  const [industry, setIndustry] = useState('');
  const [policyType, setPolicyType] = useState('');
  const [detail, setDetail] = useState<PolicyItem | null>(null);

  const policies = useApi<PolicyItem[]>(
    () =>
      api
        .get<{ items: PolicyItem[] }>('/policies', {
          limit: 100,
          ...(industry ? { industry } : {}),
        })
        .then((r) => r.items),
    [industry],
  );

  const { departments, industries, types } = useMemo(() => {
    const d = new Set<string>();
    const i = new Set<string>();
    const t = new Set<string>();
    (policies.data ?? []).forEach((p) => {
      if (p.department) d.add(p.department);
      if (p.related_industry) i.add(p.related_industry);
      if (p.policy_type) t.add(p.policy_type);
    });
    return {
      departments: Array.from(d).sort(),
      industries: Array.from(i).sort(),
      types: Array.from(t).sort(),
    };
  }, [policies.data]);

  const filtered = useMemo(() => {
    return (policies.data ?? []).filter(
      (p) =>
        (!department || p.department === department) &&
        (!policyType || p.policy_type === policyType),
    );
  }, [policies.data, department, policyType]);

  const focusItem = useMemo(
    () => (focusId && policies.data ? policies.data.find((p) => p.id === focusId) ?? null : null),
    [focusId, policies.data],
  );

  return (
    <div className="space-y-4">
      <PageHeader title="政策" desc="宏观政策与行业影响（带部门、类型、影响度标注）" />

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={department}
          onChange={setDepartment}
          options={[{ value: '', label: '全部部门' }, ...departments.map((x) => ({ value: x, label: x }))]}
        />
        <Select
          value={industry}
          onChange={setIndustry}
          options={[{ value: '', label: '全部行业' }, ...industries.map((x) => ({ value: x, label: x }))]}
        />
        <Select
          value={policyType}
          onChange={setPolicyType}
          options={[{ value: '', label: '全部类型' }, ...types.map((x) => ({ value: x, label: x }))]}
        />
        <span className="text-[11px] text-zinc-600">共 {filtered.length} 条</span>
      </div>

      <Card bodyClassName="p-0">
        {policies.loading && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}
        {policies.error && <ErrorState message={policies.error} onRetry={policies.reload} />}
        {!policies.loading && filtered.length === 0 && (
          <EmptyState title="暂无政策" desc="后端政策数据不可用或筛选无结果" icon="🏛️" />
        )}
        <div className="divide-y divide-white/5">
          {filtered
            .slice()
            .sort((a, b) => (b.impact_score ?? 0) - (a.impact_score ?? 0))
            .map((p) => (
              <button
                key={p.id}
                onClick={() => setDetail(p)}
                className="block w-full px-4 py-3.5 text-left transition hover:bg-white/[0.03]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-100">{p.title}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {p.department && <Badge>{p.department}</Badge>}
                      {p.policy_type && <Badge tone="blue">{p.policy_type}</Badge>}
                      {p.related_industry && <Badge tone="purple">{p.related_industry}</Badge>}
                    </div>
                    <div className="mt-1.5 text-[11px] text-zinc-600">{timeAgo(p.published_at)}</div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <LevelBadge value={p.impact_score} label="影响度" />
                    {p.sentiment !== null && p.sentiment !== undefined && (
                      <span
                        className={cn(
                          'num-mono text-[10px]',
                          p.sentiment > 0 ? 'text-up' : p.sentiment < 0 ? 'text-down' : 'text-zinc-500',
                        )}
                      >
                        情绪 {(p.sentiment * 100).toFixed(0)}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))}
        </div>
      </Card>

      {(detail || focusItem) && <PolicyDetailModal item={detail ?? focusItem!} onClose={() => setDetail(null)} />}
    </div>
  );
}

function PolicyDetailModal({ item, onClose }: { item: PolicyItem; onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title="政策详情" width="max-w-2xl">
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-zinc-50">{item.title}</h2>
        <div className="flex flex-wrap items-center gap-1.5">
          {item.department && <Badge>{item.department}</Badge>}
          {item.policy_type && <Badge tone="blue">{item.policy_type}</Badge>}
          {item.related_industry && <Badge tone="purple">{item.related_industry}</Badge>}
          <LevelBadge value={item.impact_score} label="影响度" />
        </div>
        <div className="text-[11px] text-zinc-500">
          发布时间：{formatDateTime(item.published_at)} · 来源：{item.source ?? '--'}
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
