import { useEffect, useId, useRef } from 'react';
import type { ApplyOption } from '../types/job';

interface ApplyOptionsModalProps {
  open: boolean;
  onClose: () => void;
  jobTitle: string;
  options: ApplyOption[];
}

export function ApplyOptionsModal({
  open,
  onClose,
  jobTitle,
  options,
}: ApplyOptionsModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => {
        panelRef.current?.querySelector<HTMLElement>('a, button')?.focus();
      }, 0);
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        window.clearTimeout(t);
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-[1px]"
        aria-label="Close dialog"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-600 dark:bg-slate-900"
      >
        <div className="border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 id={titleId} className="text-lg font-semibold text-slate-900 dark:text-white">
            Apply options
          </h2>
          <p className="mt-1 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">{jobTitle}</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ul className="flex flex-col gap-2">
            {options.map((opt, i) => (
              <li key={`${opt.applyLink}-${i}`}>
                <a
                  href={opt.applyLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/80 dark:border-slate-600 dark:bg-slate-800/50 dark:hover:border-indigo-500 dark:hover:bg-indigo-950/40"
                >
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {opt.publisher}
                  </span>
                  <span className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                    {opt.applyLink}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div className="border-t border-slate-200 px-5 py-3 dark:border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
