export interface ApplyOption {
  publisher: string;
  applyLink: string;
}

/** Normalized job from our FastAPI backend (JSearch data, server-formatted). */
export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  postedAt: string | null;
  postedDisplay: string | null;
  description: string;
  salaryDisplay: string | null;
  listingSource: string | null;
  jobPublisher?: string | null;
  jobMinSalary?: number | null;
  jobMaxSalary?: number | null;
  jobMedianSalary?: number | null;
  jobSalaryCurrency?: string | null;
  jobSalaryPeriod?: string | null;
  jobCity?: string | null;
  jobState?: string | null;
  jobCountry?: string | null;
  jobLocation?: string | null;
  employerName?: string | null;
  applyOptions?: ApplyOption[];
}

export interface JobsSearchResponse {
  jobs: Job[];
  count: number;
}
