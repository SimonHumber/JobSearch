-- Supabase setup for JobSearch
-- Run this in Supabase SQL Editor.
-- This script is destructive: it drops and recreates tables.

begin;

-- Drop existing objects first for a clean rebuild.
drop table if exists public.job_postings cascade;
drop table if exists public.companies cascade;

-- Keep everything in public schema for simple frontend reads.
create table public.companies (
    id bigserial primary key,
    name text not null unique,
    address text null,
    lat double precision null,
    long double precision null,
    created_at timestamptz not null default now()
);

create table public.job_postings (
    id text primary key,
    company_id bigint null references public.companies(id) on delete set null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create index idx_job_postings_created_at
    on public.job_postings (created_at desc);

create index idx_job_postings_company_id
    on public.job_postings (company_id);

create index idx_job_postings_payload_gin
    on public.job_postings using gin (payload jsonb_path_ops);

-- Enable RLS and only allow read access from frontend roles.
alter table public.companies enable row level security;
alter table public.job_postings enable row level security;

-- Frontend read-only policies.
drop policy if exists "anon can read companies" on public.companies;
create policy "anon can read companies"
on public.companies
for select
to anon
using (true);

drop policy if exists "anon can read job_postings" on public.job_postings;
create policy "anon can read job_postings"
on public.job_postings
for select
to anon
using (true);

drop policy if exists "authenticated can read companies" on public.companies;
create policy "authenticated can read companies"
on public.companies
for select
to authenticated
using (true);

drop policy if exists "authenticated can read job_postings" on public.job_postings;
create policy "authenticated can read job_postings"
on public.job_postings
for select
to authenticated
using (true);

-- Grant SELECT only to frontend-facing roles.
grant usage on schema public to anon, authenticated;
grant select on public.companies to anon, authenticated;
grant select on public.job_postings to anon, authenticated;

-- Ensure frontend roles cannot modify rows.
revoke insert, update, delete on public.companies from anon, authenticated;
revoke insert, update, delete on public.job_postings from anon, authenticated;

commit;
