import type { ReactNode } from 'react';
import { cn } from '../utils/format';

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-accent',
        className,
      )}
    />
  );
}

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cn('animate-pulse rounded bg-white/5', className)} style={style} />;
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn('card p-4', className)}>
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="mt-3 h-8 w-1/2" />
      <Skeleton className="mt-3 h-3 w-full" />
      <Skeleton className="mt-2 h-3 w-2/3" />
    </div>
  );
}

interface CardProps {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Card({ title, extra, children, className, bodyClassName }: CardProps) {
  return (
    <div className={cn('card flex flex-col', className)}>
      {(title !== undefined || extra !== undefined) && (
        <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
          <div className="text-sm font-medium text-zinc-200">{title}</div>
          {extra && <div className="flex items-center gap-2">{extra}</div>}
        </div>
      )}
      <div className={cn('flex-1 p-4', bodyClassName)}>{children}</div>
    </div>
  );
}

export function EmptyState({
  title = '暂无数据',
  desc,
  icon = '📭',
  action,
}: {
  title?: string;
  desc?: string;
  icon?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="text-3xl opacity-60">{icon}</div>
      <div className="text-sm font-medium text-zinc-300">{title}</div>
      {desc && <div className="max-w-sm text-xs text-zinc-500">{desc}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message = '数据加载失败',
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <div className="text-3xl">⚠️</div>
      <div className="text-sm text-zinc-300">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-md border border-white/10 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-accent/50 hover:text-white"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function PageHeader({
  title,
  desc,
  extra,
}: {
  title: string;
  desc?: string;
  extra?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">{title}</h1>
        {desc && <p className="mt-1 text-xs text-zinc-500">{desc}</p>}
      </div>
      {extra && <div className="flex items-center gap-2">{extra}</div>}
    </div>
  );
}

export function StatusDot({ color }: { color: string }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      <span
        className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40"
        style={{ backgroundColor: color }}
      />
      <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
    </span>
  );
}

export function EmptyBar() {
  return <div className="h-1 w-full rounded-full bg-white/5" />;
}
