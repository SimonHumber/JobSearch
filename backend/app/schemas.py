from pydantic import BaseModel, Field


class ApplyOptionOut(BaseModel):
    publisher: str
    applyLink: str


class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    postedAt: str | None = None
    postedDisplay: str | None = None
    description: str
    salaryDisplay: str | None = None
    listingSource: str | None = None
    jobPublisher: str | None = None
    jobMinSalary: float | int | None = None
    jobMaxSalary: float | int | None = None
    jobMedianSalary: float | int | None = None
    jobSalaryCurrency: str | None = None
    jobSalaryPeriod: str | None = None
    jobCity: str | None = None
    jobState: str | None = None
    jobCountry: str | None = None
    jobLocation: str | None = None
    employerName: str | None = None
    applyOptions: list[ApplyOptionOut] = Field(default_factory=list)


class JobsSearchResponse(BaseModel):
    jobs: list[JobOut]


class JobDescriptionIn(BaseModel):
    id: str
    description: str


class SummarizeJobsRequest(BaseModel):
    jobs: list[JobDescriptionIn]


class JobSummaryOut(BaseModel):
    id: str
    description: str = ""
    salary: str | None = None
    office_location_toronto: str | None = None
    error: str | None = None


class SummarizeJobsResponse(BaseModel):
    summaries: list[JobSummaryOut]
