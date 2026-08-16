import type { ReactNode } from 'react';
import { cn } from '../utils/format';

export function Badge({
  children,
  className,
  tone = 'zinc',
}: {
  children: ReactNode;
  className?: string;
  tone?: 'zinc' | 'red' | 'green' | 'amber' | 'blue' | 'purple';
}) {
  const tones: Record<string, string> = {
    zinc: 'bg-white/5 text-zinc-300 border-white/10',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
    green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    purple: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] leading-4',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** AI 评分徽标（0-100） */
export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <Badge>--</Badge>;
  const tone = score >= 80 ? 'red' : score >= 65 ? 'amber' : score >= 50 ? 'blue' : 'zinc';
  return (
    <Badge tone={tone} className="font-mono tabular-nums">
      <span className="text-[10px] opacity-70">AI</span>
      {score}
    </Badge>
  );
}

/** 趋势徽标：偏多=红、中性=灰、偏空=绿（红涨绿跌） */
export function TrendBadge({ trend }: { trend: string | null | undefined }) {
  if (!trend) return <Badge>--</Badge>;
  if (trend.includes('多') || trend.includes('涨')) return <Badge tone="red">{trend}</Badge>;
  if (trend.includes('空') || trend.includes('跌')) return <Badge tone="green">{trend}</Badge>;
  return <Badge tone="zinc">{trend}</Badge>;
}

/** 数据状态徽标 */
export function DataStatusBadge({ status }: { status: string | null | undefined }) {
  if (status === 'estimate') return <Badge tone="amber">盘中估值</Badge>;
  return <Badge tone="blue">最新可用数据</Badge>;
}

/** 风险等级徽标 */
export function RiskLevelBadge({ level }: { level: string | null | undefined }) {
  if (!level) return <Badge>--</Badge>;
  if (level.includes('高')) return <Badge tone="red">{level}</Badge>;
  if (level.includes('中')) return <Badge tone="amber">{level}</Badge>;
  return <Badge tone="green">{level}</Badge>;
}

/** 新闻情绪徽标 */
export function SentimentBadge({
  label,
  value,
}: {
  label: string | null | undefined;
  value?: number | null;
}) {
  const v = value ?? 0;
  if (label === 'positive' || v > 0.15)
    return <Badge tone="red">正面{v ? ` ${Math.round(v * 100)}%` : ''}</Badge>;
  if (label === 'negative' || v < -0.15)
    return <Badge tone="green">负面{v ? ` ${Math.round(Math.abs(v) * 100)}%` : ''}</Badge>;
  return <Badge tone="zinc">中性</Badge>;
}

/** 重要度/影响度徽标（0-1 或 0-100 归一化） */
export function LevelBadge({
  value,
  max = 1,
  label,
}: {
  value: number | null | undefined;
  max?: number;
  label?: string;
}) {
  if (value === null || value === undefined) return <Badge>--</Badge>;
  const ratio = value / max;
  const text = label ?? (ratio >= 0.66 ? '高' : ratio >= 0.33 ? '中' : '低');
  const tone = ratio >= 0.66 ? 'red' : ratio >= 0.33 ? 'amber' : 'zinc';
  return <Badge tone={tone}>{text}</Badge>;
}

/** 置信度徽标 */
export function ConfidenceBadge({ confidence }: { confidence: string | null | undefined }) {
  if (!confidence) return <Badge>--</Badge>;
  const c = confidence.toLowerCase();
  if (c.includes('high') || c.includes('高')) return <Badge tone="red">高置信</Badge>;
  if (c.includes('medium') || c.includes('中')) return <Badge tone="amber">中置信</Badge>;
  return <Badge tone="zinc">低置信</Badge>;
}

/** 风险严重度徽标 */
export function SeverityBadge({ severity }: { severity: string | null | undefined }) {
  if (!severity) return <Badge>--</Badge>;
  const s = severity.toLowerCase();
  if (s.includes('high') || s.includes('高')) return <Badge tone="red">高风险</Badge>;
  if (s.includes('medium') || s.includes('中')) return <Badge tone="amber">中风险</Badge>;
  return <Badge tone="green">低风险</Badge>;
}
