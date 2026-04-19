export interface CompanyMapRow {
  id: number;
  name: string;
  address: string;
  lat: number;
  long: number;
}

interface SupabaseCompanyRow {
  id?: unknown;
  name?: unknown;
  address?: unknown;
  lat?: unknown;
  long?: unknown;
}

export async function loadCompaniesForMap(): Promise<CompanyMapRow[]> {
  const baseUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.trim();
  const apiKey = (import.meta.env.VITE_SUPABASE_API_KEY as string | undefined)?.trim();
  if (!baseUrl || !apiKey) {
    throw new Error('Missing VITE_SUPABASE_URL or VITE_SUPABASE_API_KEY in frontend/.env');
  }

  const url = new URL('/rest/v1/companies', `${baseUrl.replace(/\/+$/, '')}/`);
  url.searchParams.set('select', 'id,name,address,lat,long');
  url.searchParams.set('address', 'not.is.null');
  url.searchParams.set('lat', 'not.is.null');
  url.searchParams.set('long', 'not.is.null');
  url.searchParams.set('order', 'name.asc');

  const res = await fetch(url.toString(), {
    headers: {
      apikey: apiKey,
      Authorization: `Bearer ${apiKey}`,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text.slice(0, 500) || `Request failed (${res.status})`);
  }

  const rows = (await res.json()) as SupabaseCompanyRow[];
  if (!Array.isArray(rows)) return [];

  return rows
    .map((row) => {
      const id = Number(row.id);
      const name = String(row.name ?? '').trim();
      const address = String(row.address ?? '').trim();
      const lat = Number(row.lat);
      const long = Number(row.long);
      if (!Number.isFinite(id) || !name || !address || !Number.isFinite(lat) || !Number.isFinite(long)) {
        return null;
      }
      return { id, name, address, lat, long };
    })
    .filter((row): row is CompanyMapRow => row !== null);
}
