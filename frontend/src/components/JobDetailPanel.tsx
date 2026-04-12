import { useEffect, useState } from 'react';
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

interface JobDetailPanelProps {
  job: Job | null;
  /** True while the batch Groq request for this search is in flight. */
  summariesLoading?: boolean;
}

export function JobDetailPanel({
  job,
  summariesLoading = false,
}: JobDetailPanelProps) {
  const [applyOpen, setApplyOpen] = useState(false);

  useEffect(() => {
    setApplyOpen(false);
  }, [job?.id]);

  if (!job) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden px-6 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
        Select a job to read the full description.
      </div>
    );
  }

  const posted = formatPostedAt(job);
  const salary = formatJobSalary(job);
  const source = jobSourceLabel(job);
  const applyOptions = job.applyOptions ?? [];
  const hasApplyUrls = applyOptions.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b border-slate-200 px-5 pb-4 pt-6 dark:border-slate-700 sm:px-8 sm:pt-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
            {jobTitle(job)}
          </h2>
          <button
            type="button"
            disabled={!hasApplyUrls}
            onClick={() => setApplyOpen(true)}
            title={
              hasApplyUrls ? 'View where to apply' : 'No apply links available for this listing'
            }
            className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-600 dark:disabled:text-slate-400"
          >
            Apply
          </button>
        </div>
        <p className="mt-1 text-base font-medium text-slate-800 dark:text-slate-200">
          {displayEmployer(job)}
        </p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          {formatJobLocation(job)}
          {posted ? ` · Posted ${posted}` : ''}
        </p>
        {salary && (
          <p className="mt-2 text-sm font-semibold text-emerald-700 dark:text-emerald-400">
            Salary: {salary}
          </p>
        )}
        {source && (
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Listing source: {source}
          </p>
        )}
      </header>
      <ApplyOptionsModal
        open={applyOpen && hasApplyUrls}
        onClose={() => setApplyOpen(false)}
        jobTitle={jobTitle(job)}
        options={applyOptions}
      />
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4 sm:px-8 sm:py-6">
        {(summariesLoading || job.aiSummary || job.aiSummaryError) && (
          <section
            aria-label="AI-generated summary"
            className="mb-6 rounded-lg border border-indigo-200/80 bg-indigo-50/90 px-4 py-3 dark:border-indigo-500/30 dark:bg-indigo-950/40"
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
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          {jobDescription(job)}
        </p>
      </div>
    </div>
  );
}
