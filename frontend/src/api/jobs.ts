import type { Job, JobsSearchResponse } from '../types/job';

export interface CuratedJobsPayload extends JobsSearchResponse {
  generatedAt?: string;
  query?: string;
  location?: string;
  numPages?: number;
}

interface SupabaseJobRow {
  payload?: unknown;
  created_at?: unknown;
}

export async function loadCuratedJobs(): Promise<CuratedJobsPayload> {
  const baseUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.trim();
  const apiKey = (import.meta.env.VITE_SUPABASE_API_KEY as string | undefined)?.trim();
  if (!baseUrl || !apiKey) {
    throw new Error('Missing VITE_SUPABASE_URL or VITE_SUPABASE_API_KEY in frontend/.env');
  }

  const url = `${baseUrl.replace(/\/+$/, '')}/rest/v1/job_postings?select=payload,created_at&order=created_at.desc,id.asc`;
  const res = await fetch(url, {
    headers: {
      apikey: apiKey,
      Authorization: `Bearer ${apiKey}`,
    },
  });

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

  const rows = (await res.json()) as SupabaseJobRow[];
  const safeRows = Array.isArray(rows) ? rows : [];
  const jobs: Job[] = safeRows
    .map((row) => row.payload)
    .filter((payload): payload is Job => typeof payload === 'object' && payload !== null);

  const generatedAtRaw = safeRows[0]?.created_at;
  return {
    generatedAt: typeof generatedAtRaw === 'string' ? generatedAtRaw : undefined,
    query: 'software engineer',
    location: 'Toronto',
    numPages: undefined,
    jobs,
  };
}
