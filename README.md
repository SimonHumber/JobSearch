Job search webapp that uses llm to summarize description, extract salary, and search up office location.
There's technically no backend, I hosted database on Supabase and used it's endpoint for the frontend to hit.
The "backend" folder is really just some scripts that run automatically with GitHub Actions.
Run dev.py for job search and llm summary, backfill_company_location.py to use llm to find address of each company.

0. Setup db with supabase_setup.sql, need companies table and job_postings table.
1. Use serpapi to search jobs (apply whatever filters)
2. Use llm (I'm using gemmma 4 31b) to summarize description, extract salary and address from description/db if there
3. Use llm again to go through companies table, whichever doesn't have address, use websearch tools to get address
4. Populate database with job postings, old data in job_postings table is replaced.
5. Frontend hits Supabase endpoint to read data. Maps geocoded addresses.