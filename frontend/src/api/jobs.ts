import { JSEARCH_FETCH_NUM_PAGES } from '../constants/pagination';
import type { Job, JobsSearchResponse } from '../types/job';

export interface JobSummaryResult {
  id: string;
  /** LLM summary text (JSON key `description`). */
  description: string;
  /** LLM-extracted salary when stated in the posting; null otherwise. */
  salary: string | null;
  error: string | null;
}

function buildParams(jobTitle: string, location: string, page = 1, numPages = JSEARCH_FETCH_NUM_PAGES) {
  const params = new URLSearchParams({
    jobTitle: jobTitle.trim(),
    location: location.trim(),
    page: String(page),
    numPages: String(numPages),
  });
  return params;
}

function apiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '';
}

export async function searchJobs(
  jobTitle: string,
  location: string,
  options: { page?: number; numPages?: number } = {}
): Promise<JobsSearchResponse> {
  const title = jobTitle.trim();
  const loc = location.trim();
  if (!title && !loc) {
    return { jobs: [] };
  }

  const page = options.page ?? 1;
  const numPages = options.numPages ?? JSEARCH_FETCH_NUM_PAGES;
  const params = buildParams(jobTitle, location, page, numPages);
  const url = `${apiBase()}/api/jobs/search?${params.toString()}`;

  const res = await fetch(url);

  if (!res.ok) {
    const text = await res.text();
    let detail = `Request failed (${res.status})`;
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (typeof body.detail === 'string') {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      if (text) detail = text.slice(0, 500);
    }
    throw new Error(detail);
  }

  return res.json() as Promise<JobsSearchResponse>;
}

export async function summarizeJobDescriptions(
  jobs: Pick<Job, 'id' | 'description'>[]
): Promise<JobSummaryResult[]> {
  if (jobs.length === 0) {
    return [];
  }
  const url = `${apiBase()}/api/jobs/summarize-descriptions`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      jobs: jobs.map((j) => ({ id: j.id, description: j.description })),
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = `Summary request failed (${res.status})`;
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (typeof body.detail === 'string') {
        detail = body.detail;
      }
    } catch {
      if (text) detail = text.slice(0, 500);
    }
    throw new Error(detail);
  }

  const data = (await res.json()) as { summaries?: JobSummaryResult[] };
  return Array.isArray(data.summaries) ? data.summaries : [];
}
