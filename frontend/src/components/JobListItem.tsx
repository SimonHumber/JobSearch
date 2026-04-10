import type { Job } from '../types/job';
import {
  displayEmployer,
  formatJobLocation,
  formatJobSalary,
  formatPostedAt,
  jobSourceLabel,
  jobTitle,
} from '../lib/jobDisplay';

interface JobListItemProps {
  job: Job;
  selected: boolean;
  /** When false, selected state is not shown (e.g. mobile list + modal). */
  showSelectedStyle?: boolean;
  onSelect: () => void;
}

export function JobListItem({
  job,
  selected,
  showSelectedStyle = true,
  onSelect,
}: JobListItemProps) {
  const posted = formatPostedAt(job);
  const salary = formatJobSalary(job);
  const source = jobSourceLabel(job);

  const looksSelected = showSelectedStyle && selected;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-selected={looksSelected}
      className={`w-full rounded-lg border px-4 py-3.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 ${
        looksSelected
          ? 'border-indigo-300 bg-indigo-50/90 dark:border-indigo-600 dark:bg-indigo-950/50'
          : 'border-transparent bg-white hover:bg-slate-50 dark:bg-slate-900 dark:hover:bg-slate-800/80'
      }`}
    >
      <h2 className="text-base font-semibold leading-snug text-slate-900 dark:text-slate-100">
        {jobTitle(job)}
      </h2>
      <p className="mt-0.5 text-sm font-medium text-slate-700 dark:text-slate-300">
        {displayEmployer(job)}
      </p>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        {formatJobLocation(job)}
        {posted ? ` · Posted ${posted}` : ''}
      </p>
      {salary && (
        <p className="mt-1 text-sm font-medium text-emerald-700 dark:text-emerald-400">
          {salary}
        </p>
      )}
      {source && (
        <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
          Listing source: {source}
        </p>
      )}
    </button>
  );
}
