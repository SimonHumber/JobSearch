import {
  FormEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { searchJobs, summarizeJobDescriptions } from './api/jobs';
import { JobDetailPanel } from './components/JobDetailPanel';
import { JobListItem } from './components/JobListItem';
import { MobileJobDetailSheet } from './components/MobileJobDetailSheet';
import {
  clampJsearchNumPages,
  JSEARCH_NUM_PAGES_MAX,
  JSEARCH_NUM_PAGES_MIN,
  RESULTS_PER_PAGE,
} from './constants/pagination';
import { jobKey } from './lib/jobKey';
import {
  loadPersistedJobSearch,
  savePersistedJobSearch,
} from './lib/jobSearchStorage';
import type { Job } from './types/job';
import { useMediaQuery } from './hooks/useMediaQuery';

const initialPersisted = loadPersistedJobSearch();

export default function App() {
  const [jobTitleInput, setJobTitleInput] = useState(initialPersisted.jobTitleInput);
  const [locationInput, setLocationInput] = useState(initialPersisted.locationInput);
  const [jobs, setJobs] = useState<Job[]>(initialPersisted.jobs);
  const [selectedKey, setSelectedKey] = useState<string | null>(
    initialPersisted.selectedKey
  );
  const [listPage, setListPage] = useState(initialPersisted.listPage);
  const [fetchNumPages, setFetchNumPages] = useState(initialPersisted.fetchNumPages);
  const [loading, setLoading] = useState(false);
  const [summariesLoading, setSummariesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summariesError, setSummariesError] = useState<string | null>(null);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [mobileSearchExpanded, setMobileSearchExpanded] = useState(true);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const summarizeGeneration = useRef(0);
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

  useEffect(() => {
    savePersistedJobSearch({
      jobTitleInput,
      locationInput,
      jobs,
      selectedKey,
      listPage,
      fetchNumPages,
    });
  }, [jobTitleInput, locationInput, jobs, selectedKey, listPage, fetchNumPages]);

  useEffect(() => {
    if (error && !isDesktop) {
      setMobileSearchExpanded(true);
    }
  }, [error, isDesktop]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSummariesError(null);
    setLoading(true);
    let list: Job[] = [];
    try {
      const res = await searchJobs(jobTitleInput, locationInput, {
        numPages: clampJsearchNumPages(fetchNumPages),
      });
      list = res.jobs ?? [];
      setJobs(list);
      setListPage(1);
    } catch (err) {
      setJobs([]);
      setSelectedKey(null);
      setListPage(1);
      setError(err instanceof Error ? err.message : 'Something went wrong.');
      return;
    } finally {
      setLoading(false);
    }

    if (list.length === 0) {
      return;
    }

    const batchId = ++summarizeGeneration.current;
    setSummariesLoading(true);
    try {
      const summaries = await summarizeJobDescriptions(
        list.map((j) => ({ id: j.id, description: j.description }))
      );
      if (summarizeGeneration.current !== batchId) {
        return;
      }
      const byId = new Map(summaries.map((s) => [s.id, s]));
      setJobs((prev) =>
        prev.map((j) => {
          const s = byId.get(j.id);
          if (!s) {
            return {
              ...j,
              aiSummary: null,
              aiSummaryError: 'No summary returned for this job.',
            };
          }
          const hadSearchSalary = Boolean(j.salaryDisplay?.trim());
          const llmSalary = (s.salary ?? '').trim();
          const useLlmSalary = llmSalary.length > 0 && !hadSearchSalary;
          return {
            ...j,
            aiSummary: s.description?.trim() || null,
            aiSummaryError: s.error,
            salaryDisplay: useLlmSalary ? llmSalary : j.salaryDisplay,
          };
        })
      );
    } catch (err) {
      if (summarizeGeneration.current !== batchId) {
        return;
      }
      setSummariesError(
        err instanceof Error ? err.message : 'AI summaries could not be loaded.'
      );
    } finally {
      if (summarizeGeneration.current === batchId) {
        setSummariesLoading(false);
      }
    }
  }

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
          {!isDesktop && (
            <button
              type="button"
              id="search-settings-toggle"
              aria-expanded={mobileSearchExpanded}
              aria-controls="search-settings-form"
              onClick={() => setMobileSearchExpanded((open) => !open)}
              className="mt-9 flex w-full items-center justify-between gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-left text-xs font-medium text-indigo-900 shadow-sm transition hover:bg-indigo-100 dark:border-indigo-500/40 dark:bg-indigo-500/15 dark:text-indigo-100 dark:hover:bg-indigo-500/25"
            >
              <span>
                {mobileSearchExpanded
                  ? 'Collapse search settings'
                  : 'Expand search settings'}
              </span>
              <span
                className="text-base leading-none text-indigo-600 dark:text-indigo-300"
                aria-hidden
              >
                {mobileSearchExpanded ? '\u25B2' : '\u25BC'}
              </span>
            </button>
          )}
          {(isDesktop || mobileSearchExpanded) && (
            <form
              id="search-settings-form"
              onSubmit={handleSubmit}
              className={`flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:gap-4 ${isDesktop ? 'mt-5 sm:mt-6' : 'mt-3'}`}
            >
              <label className="flex flex-1 flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
                Job title or keywords
                <input
                  type="text"
                  value={jobTitleInput}
                  onChange={(e) => setJobTitleInput(e.target.value)}
                  placeholder="e.g. React developer"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm outline-none ring-slate-400/30 placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 sm:py-2.5"
                />
              </label>
              <label className="flex flex-1 flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
                Location
                <input
                  type="text"
                  value={locationInput}
                  onChange={(e) => setLocationInput(e.target.value)}
                  placeholder="e.g. Toronto, Ontario"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm outline-none ring-slate-400/30 placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 sm:py-2.5"
                />
              </label>
              <label className="flex w-full flex-col gap-1.5 text-sm font-medium text-slate-700 sm:w-[8.5rem] sm:shrink-0 dark:text-slate-300">
                <span className="leading-tight">API pages (1-50)</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={JSEARCH_NUM_PAGES_MIN}
                  max={JSEARCH_NUM_PAGES_MAX}
                  step={1}
                  placeholder="1-50"
                  value={fetchNumPages}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '') {
                      setFetchNumPages(JSEARCH_NUM_PAGES_MIN);
                      return;
                    }
                    const n = Number.parseInt(raw, 10);
                    if (!Number.isFinite(n)) return;
                    setFetchNumPages(clampJsearchNumPages(n));
                  }}
                  onBlur={() => setFetchNumPages((p) => clampJsearchNumPages(p))}
                  className="no-input-spinner rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 sm:py-2.5"
                  aria-label="API pages to fetch, from 1 to 50"
                />
              </label>
              <button
                type="submit"
                disabled={loading}
                className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 sm:mb-0.5"
              >
                {loading ? 'Searching…' : 'Search'}
              </button>
            </form>
          )}
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
        {summariesError && (
          <div
            role="alert"
            className="mb-3 shrink-0 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
          >
            {summariesError}
          </div>
        )}

        {!loading && !error && jobs.length === 0 && (
          <div className="flex flex-1 items-center justify-center px-4 py-8">
            <p className="text-center text-slate-500 dark:text-slate-400">
              Enter a job title or location and press Search to see listings.
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
                  summariesLoading={summariesLoading}
                  scrollResetKey={selectedKey}
                />
              </div>
            </div>
            {!isDesktop && (
              <MobileJobDetailSheet
                job={selectedJob}
                open={mobileDetailOpen}
                onClose={() => setMobileDetailOpen(false)}
                summariesLoading={summariesLoading}
                scrollResetKey={selectedKey}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}
