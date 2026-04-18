import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { loadCuratedJobs } from './api/jobs';
import { JobDetailPanel } from './components/JobDetailPanel';
import { JobListItem } from './components/JobListItem';
import { MobileJobDetailSheet } from './components/MobileJobDetailSheet';
import { RESULTS_PER_PAGE } from './constants/pagination';
import { jobKey } from './lib/jobKey';
import type { Job } from './types/job';
import { useMediaQuery } from './hooks/useMediaQuery';

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [listPage, setListPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [queryLabel, setQueryLabel] = useState('software engineer');
  const [locationLabel, setLocationLabel] = useState('Toronto');
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const jobListRef = useRef<HTMLUListElement>(null);

  useLayoutEffect(() => {
    const el = jobListRef.current;
    if (el) {
      el.scrollTop = 0;
    }
  }, [listPage]);

  const totalListPages = Math.max(1, Math.ceil(jobs.length / RESULTS_PER_PAGE));
  const listOffset = (listPage - 1) * RESULTS_PER_PAGE;
  const visibleJobs = useMemo(
    () => jobs.slice(listOffset, listOffset + RESULTS_PER_PAGE),
    [jobs, listOffset]
  );

  const selectedJob =
    selectedKey === null
      ? null
      : jobs.find((job, index) => jobKey(job, index) === selectedKey) ?? null;

  useEffect(() => {
    if (jobs.length === 0) {
      setSelectedKey(null);
      setMobileDetailOpen(false);
      return;
    }
    setSelectedKey((prev) => {
      if (prev !== null && jobs.some((job, index) => jobKey(job, index) === prev)) {
        return prev;
      }
      return isDesktop ? jobKey(jobs[0], 0) : null;
    });
    setMobileDetailOpen(false);
  }, [jobs, isDesktop]);

  useEffect(() => {
    if (!isDesktop || jobs.length === 0) return;
    setSelectedKey((prev) => {
      if (prev !== null) return prev;
      return jobKey(jobs[0], 0);
    });
  }, [isDesktop, jobs]);

  const handleSelectJob = useCallback(
    (key: string) => {
      setSelectedKey(key);
      if (!isDesktop) {
        setMobileDetailOpen(true);
      }
    },
    [isDesktop]
  );

  useEffect(() => {
    if (jobs.length === 0) {
      setListPage(1);
      return;
    }
    setListPage((p) =>
      Math.min(Math.max(1, p), Math.ceil(jobs.length / RESULTS_PER_PAGE))
    );
  }, [jobs.length]);

  const runFixedSearch = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const payload = await loadCuratedJobs();
      setJobs(payload.jobs ?? []);
      setGeneratedAt(payload.generatedAt ?? null);
      setQueryLabel(payload.query?.trim() || 'software engineer');
      setLocationLabel(payload.location?.trim() || 'Toronto');
      setListPage(1);
    } catch (err) {
      setJobs([]);
      setSelectedKey(null);
      setListPage(1);
      setGeneratedAt(null);
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void runFixedSearch();
  }, [runFixedSearch]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <header className="shrink-0 border-b border-slate-200/80 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto max-w-6xl px-4 pb-4 pt-3 sm:pb-6 sm:pt-6">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-2xl font-bold leading-tight tracking-tight text-slate-900 sm:text-3xl sm:leading-tight lg:leading-normal dark:text-white">
              Job search
            </h1>
            <a
              href="https://github.com/SimonHumber/JobSearch"
              target="_blank"
              rel="noreferrer"
              aria-label="View project on GitHub"
              className="shrink-0 text-slate-700 transition hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="h-6 w-6 fill-current"
              >
                <path d="M12 0.5C5.649 0.5 0.5 5.649 0.5 12c0 5.084 3.292 9.397 7.861 10.919 0.575 0.106 0.785-0.249 0.785-0.553 0-0.273-0.01-0.996-0.015-1.955-3.198 0.695-3.873-1.541-3.873-1.541-0.523-1.328-1.277-1.681-1.277-1.681-1.045-0.714 0.079-0.699 0.079-0.699 1.155 0.081 1.762 1.186 1.762 1.186 1.027 1.76 2.694 1.251 3.351 0.956 0.104-0.744 0.402-1.251 0.731-1.538-2.553-0.29-5.238-1.276-5.238-5.68 0-1.255 0.449-2.281 1.184-3.085-0.119-0.289-0.513-1.455 0.113-3.034 0 0 0.965-0.309 3.162 1.178a10.986 10.986 0 0 1 5.759 0c2.195-1.487 3.158-1.178 3.158-1.178 0.628 1.579 0.234 2.745 0.115 3.034 0.737 0.804 1.183 1.83 1.183 3.085 0 4.414-2.689 5.386-5.251 5.671 0.413 0.355 0.781 1.055 0.781 2.126 0 1.535-0.014 2.772-0.014 3.149 0 0.306 0.207 0.664 0.79 0.551C20.211 21.393 23.5 17.082 23.5 12 23.5 5.649 18.351 0.5 12 0.5z" />
              </svg>
              <span className="sr-only">View on GitHub</span>
            </a>
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            {queryLabel} roles in {locationLabel}.
          </p>
          {generatedAt ? (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Feed generated at: {new Date(generatedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col overflow-hidden px-4 py-4">
        {error && (
          <div
            role="alert"
            className="mb-3 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200"
          >
            {error}
          </div>
        )}
        {!loading && !error && jobs.length === 0 && (
          <div className="flex flex-1 items-center justify-center px-4 py-8">
            <p className="text-center text-slate-500 dark:text-slate-400">
              No jobs found from the backend feed.
            </p>
          </div>
        )}

        {jobs.length > 0 && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80 shadow-sm dark:border-slate-700 dark:bg-slate-900/50">
            <p className="shrink-0 border-b border-slate-200 bg-slate-50/90 px-4 py-2 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-950/30 dark:text-slate-400">
              Showing {listOffset + 1}–{Math.min(listOffset + visibleJobs.length, jobs.length)} of{' '}
              {jobs.length} jobs from search
            </p>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row lg:items-stretch">
              <div
                className="flex min-h-[12rem] max-h-[42vh] flex-col border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-950/40 max-lg:max-h-none max-lg:min-h-0 max-lg:flex-1 lg:h-full lg:w-[min(100%,380px)] lg:shrink-0 lg:max-h-none lg:border-b-0 lg:border-r"
                role="tablist"
                aria-label="Job results"
              >
                <ul
                  ref={jobListRef}
                  className="min-h-0 flex-1 divide-y divide-slate-200 overflow-y-auto dark:divide-slate-700"
                >
                  {visibleJobs.map((job, i) => {
                    const index = listOffset + i;
                    const key = jobKey(job, index);
                    return (
                      <li key={key} className="p-1.5">
                        <JobListItem
                          job={job}
                          selected={selectedKey === key}
                          showSelectedStyle={isDesktop}
                          onSelect={() => handleSelectJob(key)}
                        />
                      </li>
                    );
                  })}
                </ul>
                {totalListPages > 1 && (
                  <nav
                    className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-200 bg-slate-100/90 px-2 py-2 dark:border-slate-700 dark:bg-slate-900/80"
                    aria-label="Results pages"
                  >
                    <button
                      type="button"
                      disabled={listPage <= 1}
                      onClick={() => setListPage((p) => Math.max(1, p - 1))}
                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      Previous
                    </button>
                    <span className="text-xs tabular-nums text-slate-600 dark:text-slate-400">
                      Page {listPage} of {totalListPages}
                    </span>
                    <button
                      type="button"
                      disabled={listPage >= totalListPages}
                      onClick={() =>
                        setListPage((p) => Math.min(totalListPages, p + 1))
                      }
                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      Next
                    </button>
                  </nav>
                )}
              </div>
              <div
                className="hidden min-h-0 flex-1 flex-col overflow-hidden bg-white lg:flex dark:bg-slate-900"
                role="tabpanel"
                id="job-detail-panel"
                aria-label="Job description"
              >
                <JobDetailPanel
                  job={selectedJob}
                  summariesLoading={false}
                  scrollResetKey={selectedKey}
                />
              </div>
            </div>
            {!isDesktop && (
              <MobileJobDetailSheet
                job={selectedJob}
                open={mobileDetailOpen}
                onClose={() => setMobileDetailOpen(false)}
                summariesLoading={false}
                scrollResetKey={selectedKey}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}
