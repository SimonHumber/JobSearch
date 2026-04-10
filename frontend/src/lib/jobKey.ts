import type { Job } from '../types/job';

export function jobKey(job: Job, index: number): string {
  return job.id?.trim() || `${job.title ?? ''}-${index}`;
}
