import { createPortal } from 'react-dom';
import { useToastStore } from '../store/toast';
import { cn } from '../utils/format';

const STYLES = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  error: 'border-red-500/30 bg-red-500/10 text-red-300',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
};

export default function ToastHost() {
  const { toasts, remove } = useToastStore();
  return createPortal(
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => remove(t.id)}
          className={cn(
            'pointer-events-auto animate-[slideIn_.2s_ease] rounded-lg border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur',
            STYLES[t.type],
          )}
        >
          {t.message}
        </div>
      ))}
    </div>,
    document.body,
  );
}
