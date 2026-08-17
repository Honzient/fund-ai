import { useMemo, useState } from 'react';
import { api } from '../api/client';
import type { BacktestResponse, Horizon, ModelHealthEntry, ModelHealthResponse, PredictionModel } from '../types/api';
import { cn, formatDateTime, formatPct } from '../utils/format';
import { useApi } from '../utils/hooks';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../components/ui';
import { Badge } from '../components/badges';
import { Button } from '../components/controls';

const HORIZONS: { key: Horizon; label: string; days: number }[] = [
  { key: 'short', label: '短期', days: 5 },
  { key: 'medium', label: '中期', days: 20 },
  { key: 'long', label: '长期', days: 60 },
];

const STATUS_META: Record<string, { label: string; tone: 'green' | 'amber' | 'red' | 'zinc' | 'blue' }> = {
  healthy: { label: '健康', tone: 'green' },
  warning: { label: '警告', tone: 'amber' },
  degraded: { label: '退化', tone: 'red' },
  no_model: { label: '无模型', tone: 'zinc' },
  insufficient_data: { label: '台账数据不足', tone: 'blue' },
};

function fmtPctOrDash(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return '—';
  return formatPct(v * 100, digits);
}

function HitStats({ title, stats }: { title: string; stats: { count: number | null; hit_rate: number | null } | null | undefined }) {
  if (!stats || stats.count === null) {
    return (
      <div>
        <div className="text-[11px] text-zinc-600">{title}</div>
        <div className="num-mono mt-0.5 text-sm text-zinc-500">暂无数据</div>
      </div>
    );
  }
  return (
    <div>
      <div className="text-[11px] text-zinc-600">{title}（{stats.count} 次）</div>
      <div className="num-mono mt-0.5 text-sm font-semibold text-zinc-100">{fmtPctOrDash(stats.hit_rate)}</div>
    </div>
  );
}

function HealthCard({ horizon, entry }: { horizon: string; entry: ModelHealthEntry }) {
  const statusMeta = STATUS_META[entry.status] ?? STATUS_META.no_model;
  const champion = entry.champion;
  const metrics = champion?.metrics;
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          {HORIZONS.find((h) => h.key === horizon)?.label ?? horizon}
          <Badge tone={statusMeta.tone}>{statusMeta.label}</Badge>
        </span>
      }
      bodyClassName="p-4 space-y-3"
    >
      {!champion && (
        <EmptyState
          title="尚无可用模型"
          desc="数据不足或尚未训练。点击右上角「重新训练」在后台训练模型。"
          icon="🧪"
        />
      )}
      {champion && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
            <span className="num-mono rounded bg-white/5 px-1.5 py-0.5 font-medium text-zinc-100">
              {champion.model_name ?? '—'} {champion.version ?? ''}
            </span>
            <span className="text-zinc-500">训练于 {formatDateTime(champion.trained_at)}</span>
            <span className="text-zinc-500">校准 {champion.calibration_method ?? '—'}</span>
            <span className="num-mono ml-auto font-semibold text-accent">
              ModelScore {champion.model_score != null ? champion.model_score.toFixed(1) : '—'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {(
              [
                ['Brier', metrics?.brier_score, 3],
                ['LogLoss', metrics?.log_loss, 3],
                ['Bal.Acc', metrics?.balanced_accuracy, 3],
                ['ECE', metrics?.ece, 3],
                ['HitRate', metrics?.hit_rate, 3],
              ] as [string, number | null | undefined, number][]
            ).map(([label, v, d]) => (
              <div key={label} className="rounded-lg border border-white/5 bg-surface-2 p-2">
                <div className="text-[10px] text-zinc-600">{label}</div>
                <div className="num-mono mt-0.5 text-sm font-medium text-zinc-100">
                  {v === null || v === undefined ? '—' : v.toFixed(d)}
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2 border-t border-white/5 pt-3">
            <HitStats title="近30次命中率" stats={entry.ledger?.last_30} />
            <HitStats title="近100次命中率" stats={entry.ledger?.last_100} />
            <HitStats title="全部命中率" stats={entry.ledger?.all} />
          </div>
          {champion.baseline_comparison && (
            <div className="border-t border-white/5 pt-2">
              <div className="mb-1 text-[11px] text-zinc-600">验证期基线对比（ModelScore / Bal.Acc）</div>
              <div className="space-y-0.5">
                {Object.entries(champion.baseline_comparison).map(
                  ([name, m]: [string, { model_score: number | null; balanced_accuracy: number | null }]) => (
                    <div key={name} className="flex items-center justify-between text-[11px]">
                      <span className={cn('text-zinc-400', name === champion.model_name && 'font-medium text-accent')}>
                        {name}
                      </span>
                      <span className="num-mono text-zinc-300">
                        {m.model_score != null ? m.model_score.toFixed(1) : '—'} /{' '}
                        {m.balanced_accuracy != null ? m.balanced_accuracy.toFixed(2) : '—'}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </div>
          )}
          <p className="text-[11px] leading-relaxed text-zinc-500">{entry.note}</p>
        </>
      )}
    </Card>
  );
}

function BacktestPanel() {
  const [horizon, setHorizon] = useState<Horizon>('short');
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const task = await api.post<{ task_id: number }>('/prediction/backtest', { horizon });
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const r = await api.get<{ status: string; result: BacktestResponse | null; error: string | null }>(
          `/prediction/backtest/result/${task.task_id}`,
        );
        if (r.status === 'success' && r.result) {
          setResult(r.result);
          break;
        }
        if (r.status === 'failed') {
          setError(r.error ?? '回测失败');
          break;
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '回测失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="Walk-Forward 回测（Purged 窗口 + 基线对比）" bodyClassName="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <select
          value={horizon}
          onChange={(e) => setHorizon(e.target.value as Horizon)}
          className="rounded-md border border-white/10 bg-surface-2 px-2 py-1.5 text-xs text-zinc-200 outline-none"
        >
          {HORIZONS.map((h) => (
            <option key={h.key} value={h.key}>
              {h.label}（{h.days}日）
            </option>
          ))}
        </select>
        <Button variant="ghost" onClick={() => void run()} disabled={loading} className="text-xs">
          {loading ? '回测中…' : '运行回测'}
        </Button>
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>
      {result && !result.available && (
        <EmptyState title="回测不可用" desc={result.reason ?? '样本不足'} icon="📉" />
      )}
      {result?.available && result.metrics && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(
              [
                ['Accuracy', result.metrics.accuracy, 2],
                ['Bal.Acc', result.metrics.balanced_accuracy, 2],
                ['Brier', result.metrics.brier_score, 3],
                ['ECE', result.metrics.ece, 3],
                ['HitRate', result.metrics.hit_rate, 2],
                ['ModelScore', result.metrics.model_score, 1],
              ] as [string, number | null | undefined, number][]
            ).map(([label, v, d]) => (
              <div key={label} className="rounded-lg border border-white/5 bg-surface-2 p-2">
                <div className="text-[10px] text-zinc-600">{label}</div>
                <div className="num-mono mt-0.5 text-sm font-medium text-zinc-100">
                  {v === null || v === undefined ? '—' : v.toFixed(d)}
                </div>
              </div>
            ))}
          </div>
          {result.baselines && (
            <div className="border-t border-white/5 pt-2">
              <div className="mb-1 text-[11px] text-zinc-600">同窗口基线对比</div>
              <div className="space-y-0.5">
                {Object.entries(result.baselines).map(([name, m]) => (
                  <div key={name} className="flex items-center justify-between text-[11px]">
                    <span className="text-zinc-400">{name}</span>
                    <span className="num-mono text-zinc-300">
                      acc {m.accuracy != null ? (m.accuracy * 100).toFixed(1) : '—'}% · score{' '}
                      {m.model_score != null ? m.model_score.toFixed(1) : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <p className="text-[10px] text-zinc-600">{result.disclaimer}</p>
        </>
      )}
    </Card>
  );
}

export default function Models() {
  const health = useApi<ModelHealthResponse>(() => api.get('/prediction/health'), []);
  const models = useApi<PredictionModel[]>(() => api.get('/prediction/models'), []);
  const [retraining, setRetraining] = useState(false);

  const retrain = async (horizon?: Horizon) => {
    setRetraining(true);
    try {
      await api.post(`/prediction/retrain${horizon ? `?horizon=${horizon}` : ''}`);
      window.alert('已提交后台训练任务，几分钟后可刷新查看（模型未就绪期间预测自动使用统计基线）。');
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '提交失败');
    } finally {
      setRetraining(false);
    }
  };

  const sortedModels = useMemo(
    () => (models.data ?? []).slice().sort((a, b) => String(b.version).localeCompare(String(a.version))),
    [models.data],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="模型健康"
        desc="Champion 模型、验证指标、基线对比与预测台账真实命中率"
        extra={
          <Button variant="primary" onClick={() => void retrain()} disabled={retraining} className="text-xs">
            {retraining ? '提交中…' : '重新训练全部周期'}
          </Button>
        }
      />

      {health.loading && (
        <div className="grid gap-3 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-xl" />
          ))}
        </div>
      )}
      {health.error && <ErrorState message={health.error} onRetry={health.reload} />}
      {!health.loading && !health.error && (
        <div className="grid gap-3 lg:grid-cols-3">
          {HORIZONS.map((h) => {
            const entry = health.data?.[h.key];
            return entry ? (
              <HealthCard key={h.key} horizon={h.key} entry={entry} />
            ) : (
              <Card key={h.key} title={h.label}>
                <EmptyState title="暂无数据" desc="后端未返回该周期健康信息" icon="🧪" />
              </Card>
            );
          })}
        </div>
      )}

      <BacktestPanel />

      <Card title="模型版本历史" bodyClassName="p-0">
        {models.loading && <Skeleton className="m-2 h-24" />}
        {!models.loading && sortedModels.length === 0 && (
          <EmptyState title="暂无模型版本" desc="点击右上角「重新训练」生成第一个模型" icon="🧪" />
        )}
        {sortedModels.length > 0 && (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/5 text-[11px] text-zinc-500">
                <th className="px-3 py-2">版本</th>
                <th className="px-3 py-2">周期</th>
                <th className="px-3 py-2">模型</th>
                <th className="px-3 py-2">校准</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">训练时间</th>
                <th className="px-3 py-2">样本</th>
                <th className="px-3 py-2">ModelScore</th>
              </tr>
            </thead>
            <tbody>
              {sortedModels.map((m) => (
                <tr key={`${m.horizon}-${m.version}`} className="border-b border-white/5 last:border-0">
                  <td className="num-mono px-3 py-2 text-zinc-100">
                    {m.version} {m.champion && <span className="text-accent">★</span>}
                  </td>
                  <td className="px-3 py-2 text-zinc-400">{m.horizon ?? '—'}</td>
                  <td className="px-3 py-2 text-zinc-300">{m.model_name ?? '—'}</td>
                  <td className="px-3 py-2 text-zinc-400">{m.calibration_method ?? '—'}</td>
                  <td className="px-3 py-2">
                    <Badge tone={m.status === 'retired' ? 'zinc' : m.status === 'active' ? 'green' : 'amber'}>
                      {m.status ?? '—'}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-zinc-500">{formatDateTime(m.trained_at)}</td>
                  <td className="num-mono px-3 py-2 text-zinc-400">{m.samples ?? '—'}</td>
                  <td className="num-mono px-3 py-2 text-zinc-300">
                    {m.metrics?.model_score != null ? m.metrics.model_score.toFixed(1) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
