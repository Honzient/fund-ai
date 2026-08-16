import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../utils/format';

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: ReactNode;
  footer?: ReactNode;
  width?: string;
}

/** 居中 Modal */
export function Modal({ open, onClose, children, title, footer, width = 'max-w-lg' }: OverlayProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className={cn(
          'relative z-10 flex max-h-[85vh] w-full flex-col overflow-hidden rounded-xl border border-white/10 bg-surface shadow-2xl',
          width,
        )}
      >
        {title !== undefined && (
          <div className="flex items-center justify-between border-b border-white/5 px-5 py-3.5">
            <div className="text-sm font-semibold text-zinc-100">{title}</div>
            <button
              onClick={onClose}
              className="rounded p-1 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-white/5 px-5 py-3">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** 右侧抽屉 */
export function Drawer({ open, onClose, children, title, width = 'max-w-xl' }: OverlayProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className={cn(
          'absolute right-0 top-0 flex h-full w-full flex-col overflow-hidden border-l border-white/10 bg-surface shadow-2xl',
          width,
        )}
      >
        {title !== undefined && (
          <div className="flex items-center justify-between border-b border-white/5 px-5 py-3.5">
            <div className="text-sm font-semibold text-zinc-100">{title}</div>
            <button
              onClick={onClose}
              className="rounded p-1 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
