/** Jobs shown per page in the list UI. */
export const RESULTS_PER_PAGE = 15;

/** JSearch `num_pages` query param: min/max allowed by the API wrapper. */
export const JSEARCH_NUM_PAGES_MIN = 1;
export const JSEARCH_NUM_PAGES_MAX = 50;

/**
 * JSearch `/search`: default number of pages to fetch in one request (often ~10 jobs per page).
 * The provider allows up to 50 pages per query.
 */
export const JSEARCH_FETCH_NUM_PAGES = 50;

export function clampJsearchNumPages(n: number): number {
  if (!Number.isFinite(n)) return JSEARCH_FETCH_NUM_PAGES;
  return Math.min(
    Math.max(Math.floor(n), JSEARCH_NUM_PAGES_MIN),
    JSEARCH_NUM_PAGES_MAX
  );
}
