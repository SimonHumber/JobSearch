import { importLibrary, setOptions } from '@googlemaps/js-api-loader';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { loadCompaniesForMap, type CompanyMapRow } from '../api/companies';

const DEFAULT_CENTER = { lat: 43.6532, lng: -79.3832 };

export function CompaniesMapPage() {
  const [companies, setCompanies] = useState<CompanyMapRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapsConfiguredRef = useRef(false);

  const mapApiKey = useMemo(() => (import.meta.env.MAP_API_KEY as string | undefined)?.trim() || '', []);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await loadCompaniesForMap();
        setCompanies(rows);
      } catch (err) {
        setCompanies([]);
        setError(err instanceof Error ? err.message : 'Failed to load companies.');
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, []);

  useEffect(() => {
    if (!mapApiKey) {
      setMapError('Missing MAP_API_KEY in frontend .env.');
      return;
    }
    if (!mapRef.current) return;

    let disposed = false;
    const markerList: Array<{ setMap: (map: null) => void }> = [];

    const renderMap = async () => {
      try {
        setMapError(null);
        if (!mapsConfiguredRef.current) {
          setOptions({
            key: mapApiKey,
            v: 'weekly',
          });
          mapsConfiguredRef.current = true;
        }
        await importLibrary('maps');
        if (disposed || !mapRef.current) return;

        const googleMaps = (window as Window & { google?: any }).google?.maps;
        if (!googleMaps) {
          setMapError('Google Maps SDK did not initialize.');
          return;
        }

        const map = new googleMaps.Map(mapRef.current, {
          center: DEFAULT_CENTER,
          zoom: 10,
          streetViewControl: false,
          mapTypeControl: false,
        });

        if (companies.length === 0) return;

        const bounds = new googleMaps.LatLngBounds();
        const grouped = new Map<string, CompanyMapRow[]>();
        companies.forEach((company) => {
          const key = `${company.lat.toFixed(6)},${company.long.toFixed(6)}`;
          const existing = grouped.get(key);
          if (existing) {
            existing.push(company);
          } else {
            grouped.set(key, [company]);
          }
        });

        grouped.forEach((groupCompanies) => {
          const first = groupCompanies[0];
          const position = { lat: first.lat, lng: first.long };
          const isStacked = groupCompanies.length > 1;
          const marker = new googleMaps.Marker({
            position,
            map,
            title: isStacked ? `${groupCompanies.length} companies` : groupCompanies[0].name,
            icon: {
              path: googleMaps.SymbolPath.CIRCLE,
              scale: isStacked ? 10 : 7,
              fillColor: '#4f46e5',
              fillOpacity: 1,
              strokeColor: '#ffffff',
              strokeWeight: 1.5,
            },
            label: isStacked
              ? {
                text: String(groupCompanies.length),
                color: '#ffffff',
                fontSize: '11px',
                fontWeight: '700',
              }
              : undefined,
          });
          const popupItems = groupCompanies
            .map(
              (company) =>
                `<li style="margin: 0.35rem 0;">
                  <strong>${company.name}</strong><br/>
                  <span>${company.address}</span>
                </li>`
            )
            .join('');
          const popupHtml =
            groupCompanies.length === 1
              ? `<div style="max-width:260px">
                  <strong>${groupCompanies[0].name}</strong><br/>
                  <span>${groupCompanies[0].address}</span>
                </div>`
              : `<div style="max-width:300px">
                  <strong>${groupCompanies.length} companies at this location</strong>
                  <ul style="margin: 0.5rem 0 0 1rem; padding: 0;">${popupItems}</ul>
                </div>`;
          const infoWindow = new googleMaps.InfoWindow({ content: popupHtml });
          marker.addListener('click', () => {
            infoWindow.open({ anchor: marker, map });
          });
          markerList.push(marker);
          bounds.extend(position);
        });

        if (companies.length === 1) {
          map.setCenter({ lat: companies[0].lat, lng: companies[0].long });
          map.setZoom(13);
        } else {
          map.fitBounds(bounds, 64);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to render map.';
        setMapError(message);
      }
    };

    void renderMap();

    return () => {
      disposed = true;
      markerList.forEach((marker) => marker.setMap(null));
    };
  }, [companies, mapApiKey]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <header className="shrink-0 border-b border-slate-200/80 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Companies map
            </h1>
          </div>
          <Link
            to="/"
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Back to jobs
          </Link>
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col gap-3 px-4 py-4">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
            {error}
          </div>
        ) : null}
        {mapError ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-200">
            {mapError}
          </div>
        ) : null}
        {loading ? <p className="text-sm text-slate-600 dark:text-slate-300">Loading companies…</p> : null}

        <section className="min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div ref={mapRef} className="h-full min-h-[360px] w-full" />
        </section>

        <section className="max-h-56 overflow-y-auto rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
            Companies on map ({companies.length})
          </h2>
          {companies.length === 0 ? (
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              No companies have both address and coordinates yet.
            </p>
          ) : (
            <ul className="mt-2 space-y-2 text-sm">
              {companies.map((company) => (
                <li key={company.id} className="rounded-md border border-slate-200 px-2 py-1 dark:border-slate-700">
                  <p className="font-medium text-slate-900 dark:text-white">{company.name}</p>
                  <p className="text-slate-600 dark:text-slate-300">{company.address}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
