import { RESULTS_PER_PAGE } from '../constants/pagination';
import type { Job } from '../types/job';
import { jobKey } from './jobKey';

const STORAGE_KEY = 'jobsearch:persist:v2';

export interface PersistedJobSearchState {
  jobTitleInput: string;
  locationInput: string;
  jobs: Job[];
  selectedKey: string | null;
  /** 1-based index for client-side list pagination. */
  listPage: number;
}

const defaults: PersistedJobSearchState = {
  jobTitleInput: '',
  locationInput: 'Toronto, Ontario',
  jobs: [],
  selectedKey: null,
  listPage: 1,
};

function normalizeListPage(jobCount: number, raw: unknown): number {
  if (jobCount === 0) return 1;
  const totalPages = Math.max(1, Math.ceil(jobCount / RESULTS_PER_PAGE));
  const n =
    typeof raw === 'number' && Number.isFinite(raw) ? Math.floor(raw) : 1;
  return Math.min(Math.max(1, n), totalPages);
}

function autoSelectFirstJob(): boolean {
  if (typeof window === 'undefined') return true;
  return window.matchMedia('(min-width: 1024px)').matches;
}

function normalizeSelectedKey(
  jobs: Job[],
  selectedKey: string | null,
  pickFirstWhenMissing: boolean
): string | null {
  if (jobs.length === 0) return null;
  if (selectedKey !== null && jobs.some((job, index) => jobKey(job, index) === selectedKey)) {
    return selectedKey;
  }
  return pickFirstWhenMissing ? jobKey(jobs[0], 0) : null;
}

export function loadPersistedJobSearch(): PersistedJobSearchState {
  if (typeof localStorage === 'undefined') return { ...defaults };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaults };

    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== 'object') return { ...defaults };

    const o = data as Record<string, unknown>;
    if (o.v !== 2) return { ...defaults };

    const jobs = Array.isArray(o.jobs) ? (o.jobs as Job[]) : [];
    const jobTitleInput = typeof o.jobTitleInput === 'string' ? o.jobTitleInput : '';
    const locationInput = typeof o.locationInput === 'string' ? o.locationInput : '';
    const rawKey = o.selectedKey;
    const selectedKey =
      rawKey === null ? null : typeof rawKey === 'string' ? rawKey : null;

    return {
      jobTitleInput,
      locationInput,
      jobs,
      selectedKey: normalizeSelectedKey(jobs, selectedKey, autoSelectFirstJob()),
      listPage: normalizeListPage(jobs.length, o.listPage),
    };
  } catch {
    return { ...defaults };
  }
}

export function savePersistedJobSearch(state: PersistedJobSearchState): void {
  if (typeof localStorage === 'undefined') return;
  try {
    const payload = {
      v: 2 as const,
      jobTitleInput: state.jobTitleInput,
      locationInput: state.locationInput,
      jobs: state.jobs,
      selectedKey: state.selectedKey,
      listPage: state.listPage,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* quota or private mode */
  }
}
