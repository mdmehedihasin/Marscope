// API client. If the backend is unreachable it falls back to the bundled demo snapshot (public/demo/snapshot.json),
// so the Demo Mission still works with no server and no internet. The UI shows which mode is active.
export class ApiError extends Error {}
let offline = false;
let snap: any = null;
export const isOffline = () => offline;

async function snapshot() {
  if (!snap) {
    const r = await fetch('./demo/snapshot.json');
    if (!r.ok) throw new ApiError('Backend unavailable and no offline snapshot found.');
    snap = await r.json();
  }
  return snap;
}

async function fromSnapshot(path: string, body?: any): Promise<any> {
  const s = await snapshot();
  const sameEnds = (b: any) =>
    !b ||
    ((!b.start || (b.start.lat === s.default_start.lat && b.start.lon === s.default_start.lon)) &&
      (!b.dest || (b.dest.lat === s.default_dest.lat && b.dest.lon === s.default_dest.lon)) &&
      (!b.grid || b.grid === (s.default_grid || 'routing')));
  const u = new URL(path, 'http://x');
  const p = u.pathname;
  if (p === '/api/health') return { ok: true, data_mode: s.metadata.data_mode, offline: true };
  if (p in s.get) return s.get[p];
  if (p === '/api/routes/compare' || p === '/api/routes') {
    if (!sameEnds(body))
      throw new ApiError(
        'Offline snapshot contains only the Demo Mission routes (default endpoints, 1/512° routing grid). Start the backend to plan other routes.',
      );
    const routes = s.get['/api/routes/compare'].routes;
    return p === '/api/routes' ? routes.find((r: any) => r.mode === (body?.mode || 'balanced')) : { routes };
  }
  if (p.endsWith('/evidence')) {
    const rid = p.split('/')[3];
    const seg = u.searchParams.get('segment')!;
    const e = s.evidence?.[rid]?.[seg];
    if (!e) throw new ApiError('Evidence not in offline snapshot.');
    return e;
  }
  if (p === '/api/crew-brief') {
    const b = s.briefs?.[body.route_id];
    if (!b) throw new ApiError('Brief not in offline snapshot.');
    return b;
  }
  if (p === '/api/cell') throw new ApiError('Cell inspection needs the backend (offline snapshot).');
  throw new ApiError('Not available offline.');
}

export async function api<T = any>(path: string, body?: any): Promise<T> {
  if (!offline) {
    try {
      const r = await fetch(
        path,
        body
          ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
          : undefined,
      );
      const ct = r.headers.get('content-type') || '';
      if (!ct.includes('json')) throw new TypeError('no backend');
      const j = await r.json();
      if (!r.ok) throw new ApiError(j.error || j.detail || 'Request failed');
      return j as T;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      offline = true;
    }
  }
  return fromSnapshot(path, body) as Promise<T>;
}
export const layerUrl = (png: string) => (offline ? `./demo/layers/${png}` : `/layers/${png}`);
