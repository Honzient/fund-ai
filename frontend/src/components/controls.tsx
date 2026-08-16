import type { ReactNode } from 'react';
import { cn } from '../utils/format';

export function Button({
  children,
  onClick,
  variant = 'default',
  size = 'md',
  disabled,
  className,
  type = 'button',
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'default' | 'primary' | 'ghost' | 'danger' | 'accent';
  size?: 'sm' | 'md';
  disabled?: boolean;
  className?: string;
  type?: 'button' | 'submit';
}) {
  const variants: Record<string, string> = {
    default: 'border border-white/10 bg-white/5 text-zinc-200 hover:bg-white/10 hover:border-white/20',
    primary: 'bg-accent text-white hover:bg-blue-600 shadow-glow',
    accent: 'bg-red-500/90 text-white hover:bg-red-500',
    danger: 'border border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20',
    ghost: 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5',
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-40',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-sm',
        variants[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Input({
  value,
  onChange,
  placeholder,
  className,
  type = 'text',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(
        'w-full rounded-md border border-white/10 bg-surface-2 px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition focus:border-accent/60 focus:ring-1 focus:ring-accent/30',
        className,
      )}
    />
  );
}

export function Select({
  value,
  onChange,
  options,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        'rounded-md border border-white/10 bg-surface-2 px-2.5 py-1.5 text-sm text-zinc-100 outline-none transition focus:border-accent/60',
        className,
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** 分段切换（如 日/周/月、1M/3M/6M） */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  size = 'sm',
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  size?: 'sm' | 'xs';
}) {
  return (
    <div className="inline-flex items-center rounded-md border border-white/10 bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded px-2.5 font-medium transition',
            size === 'xs' ? 'py-0.5 text-[11px]' : 'py-1 text-xs',
            value === o.value
              ? 'bg-accent/20 text-accent shadow-sm'
              : 'text-zinc-400 hover:text-zinc-100',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2"
    >
      <span
        className={cn(
          'relative inline-flex h-5 w-9 items-center rounded-full transition',
          checked ? 'bg-accent' : 'bg-white/10',
        )}
      >
        <span
          className={cn(
            'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition',
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]',
          )}
        />
      </span>
      {label && <span className="text-sm text-zinc-300">{label}</span>}
    </button>
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-white/20 bg-surface-2 accent-blue-500"
      />
      {label !== undefined && <span className="text-sm text-zinc-300">{label}</span>}
    </label>
  );
}
