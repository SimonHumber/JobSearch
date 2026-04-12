import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Job } from '../types/job';
import { ApplyOptionsModal } from './ApplyOptionsModal';
import {
  displayEmployer,
  formatJobLocation,
  formatJobSalary,
  formatPostedAt,
  jobDescription,
  jobSourceLabel,
  jobTitle,
} from '../lib/jobDisplay';

const CLOSE_MS = 300;

interface MobileJobDetailSheetProps {
  job: Job | null;
  open: boolean;
  onClose: () => void;
  summariesLoading?: boolean;
}

export function MobileJobDetailSheet({
  job,
  open,
  onClose,
  summariesLoading = false,
}: MobileJobDetailSheetProps) {
  const headingId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const enterInnerRafRef = useRef(0);
  const [present, setPresent] = useState(false);
  /** False until next frame after mount so open animates from translateY(100%). */
  const [entered, setEntered] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  useLayoutEffect(() => {
    if (open && job) {
      setPresent(true);
      setEntered(false);
      const outerRaf = requestAnimationFrame(() => {
        enterInnerRafRef.current = requestAnimationFrame(() => setEntered(true));
      });
      return () => {
        cancelAnimationFrame(outerRaf);
        cancelAnimationFrame(enterInnerRafRef.current);
      };
    }
    setEntered(false);
    const t = window.setTimeout(() => setPresent(false), CLOSE_MS);
    return () => window.clearTimeout(t);
  }, [open, job]);

  useEffect(() => {
    setApplyOpen(false);
  }, [job?.id]);

  useEffect(() => {
    if (!present || !open || !job) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [present, open, job, onClose]);

  useEffect(() => {
    if (!present || !open || !job) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [present, open, job]);

  useEffect(() => {
    if (!present || !open || !job || !entered) return;
    const t = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>('button')?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [present, open, job, entered]);

  if (!job || !present) return null;

  const translateY = open && entered ? '0px' : '100%';
  const transition =
    open && !entered ? 'none' : `transform ${CLOSE_MS}ms cubic-bezier(0.32, 0.72, 0, 1)`;
  const posted = formatPostedAt(job);
  const salary = formatJobSalary(job);
  const source = jobSourceLabel(job);
  const applyOptions = job.applyOptions ?? [];
  const hasApplyUrls = applyOptions.length > 0;

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
      className="bg-white dark:bg-slate-900"
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        top: 0,
        bottom: 0,
        width: '100%',
        height: '100%',
        maxHeight: '100dvh',
        zIndex: 2147483646,
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        paddingTop: 'env(safe-area-inset-top, 0px)',
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        transform: `translateY(${translateY})`,
        transition,
        overflow: 'hidden',
      }}
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <h2
          id={headingId}
          className="min-w-0 flex-1 text-base font-semibold leading-snug text-slate-900 dark:text-white"
        >
          {jobTitle(job)}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded-lg px-3 py-1.5 text-sm font-semibold text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950/50"
        >
          Done
        </button>
      </div>
      <div
        className="min-h-0 flex-1 touch-pan-y overscroll-y-contain px-4 py-4"
        style={{
          overflowY: 'auto',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 dark:border-slate-700">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <p className="text-base font-medium text-slate-800 dark:text-slate-200">
              {displayEmployer(job)}
            </p>
            <button
              type="button"
              disabled={!hasApplyUrls}
              onClick={() => setApplyOpen(true)}
              title={
                hasApplyUrls ? 'View where to apply' : 'No apply links available for this listing'
              }
              className="shrink-0 self-start rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-600 dark:disabled:text-slate-400"
            >
              Apply
            </button>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {formatJobLocation(job)}
            {posted ? ` · Posted ${posted}` : ''}
          </p>
          {salary && (
            <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
              Salary: {salary}
            </p>
          )}
          {source && (
            <p className="text-xs text-slate-500 dark:text-slate-400">Listing source: {source}</p>
          )}
        </div>
        {(summariesLoading || job.aiSummary || job.aiSummaryError) && (
          <section
            aria-label="AI-generated summary"
            className="mt-4 rounded-lg border border-indigo-200/80 bg-indigo-50/90 px-3 py-3 dark:border-indigo-500/30 dark:bg-indigo-950/40"
          >
            <h3 className="text-xs font-semibold uppercase tracking-wide text-indigo-800 dark:text-indigo-200">
              AI summary
            </h3>
            {summariesLoading && !job.aiSummary && !job.aiSummaryError ? (
              <p className="mt-2 text-sm text-indigo-900/80 dark:text-indigo-100/80">
                Generating summary…
              </p>
            ) : null}
            {job.aiSummaryError ? (
              <p className="mt-2 text-sm text-red-700 dark:text-red-300" role="alert">
                {job.aiSummaryError}
              </p>
            ) : null}
            {job.aiSummary ? (
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-800 dark:text-slate-200">
                {job.aiSummary}
              </p>
            ) : null}
          </section>
        )}
        <h3 className="sr-only">Job description</h3>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          {jobDescription(job)}
        </p>
      </div>
      <ApplyOptionsModal
        open={applyOpen && hasApplyUrls}
        onClose={() => setApplyOpen(false)}
        jobTitle={jobTitle(job)}
        options={applyOptions}
      />
    </div>,
    document.body
  );
}
