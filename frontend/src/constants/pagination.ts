/** Jobs shown per page in the list UI. */
export const RESULTS_PER_PAGE = 15;

/**
 * JSearch `/search`: how many backend pages to fetch in one request (often ~10 jobs each).
 * The provider documents up to ~500 listings per query;50 pages is a practical upper bound.
 */
export const JSEARCH_FETCH_NUM_PAGES = 50;
