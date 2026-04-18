import type { Job, JobsSearchResponse } from '../types/job';

export interface CuratedJobsPayload extends JobsSearchResponse {
  generatedAt?: string;
  query?: string;
  location?: string;
  numPages?: number;
}

export async function loadCuratedJobs(): Promise<CuratedJobsPayload> {
  const url = '/jobs.json';
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

  const data = (await res.json()) as Partial<CuratedJobsPayload>;
  const jobs = Array.isArray(data.jobs) ? (data.jobs as Job[]) : [];
  return {
    generatedAt: typeof data.generatedAt === 'string' ? data.generatedAt : undefined,
    query: typeof data.query === 'string' ? data.query : undefined,
    location: typeof data.location === 'string' ? data.location : undefined,
    numPages: typeof data.numPages === 'number' ? data.numPages : undefined,
    jobs,
  };
}
