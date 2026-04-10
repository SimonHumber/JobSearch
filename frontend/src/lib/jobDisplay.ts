import type { Job } from '../types/job';

export function formatJobLocation(job: Job): string {
  return job.location?.trim() || 'Location not listed';
}

export function jobTitle(job: Job): string {
  return job.title?.trim() || 'Untitled role';
}

/** Company / employer line (normalized on server). */
export function displayEmployer(job: Job): string {
  return job.company?.trim() || 'Company not listed';
}

export function jobSourceLabel(job: Job): string | null {
  return job.listingSource?.trim() || null;
}

export function formatJobSalary(job: Job): string | null {
  return job.salaryDisplay?.trim() || null;
}

export function formatPostedAt(job: Job): string | null {
  return job.postedDisplay?.trim() || null;
}

export function jobDescription(job: Job): string {
  return job.description?.trim() || 'No description provided.';
}
