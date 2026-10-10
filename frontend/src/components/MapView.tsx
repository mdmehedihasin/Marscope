import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { api, layerUrl } from '../api';
import type { Layer, Meta, Overlay, ProfilePt, Pt, Route, Target } from '../types';

export const MODE_COLOR: Record<string, string> = {
  traversability: '#d8b98e',
  science: '#e0a84a',
  balanced: '#74d6d2',
};
interface P {
  meta: Meta;
  layers: Layer[];
  overlays: Overlay[];
  visible: Record<string, boolean>;
  targets: Target[];
  routes: Route[];
  selRoute: string | null;
  selSeg: string | null;
  hover: ProfilePt | null;
  start: Pt;
  dest: Pt;
  picking: 'start' | 'dest' | null;
  onPick: (k: 'start' | 'dest', p: Pt) => void;
  onRoute: (id: string) => void;
  onSeg: (id: string) => void;
  onTarget: (t: Target) => void;
  onScale?: (i: number) => void;
}

export default function MapView(p: P) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const g = useRef<Record<string, L.LayerGroup>>({});
  const imgs = useRef<Record<string, L.ImageOverlay>>({});
  const [read, setRead] = useState<string>('Move over the map · click to inspect a cell');
  const [scale, setScale] = useState({ px: 100, km: 5 });
  const cb = useRef(p);
  cb.current = p;
  const b = p.meta.region.bounds;
  const bounds = L.latLngBounds([b.lat_min, b.lon_min], [b.lat_max, b.lon_max]);

  useEffect(() => {
    const m = L.map(el.current!, {
      crs: L.CRS.Simple,
      zoomSnap: 0.25,
      minZoom: 4,
      maxZoom: 13,
      attributionControl: true,
      zoomControl: true,
      maxBounds: bounds.pad(0.25),
    });
    m.fitBounds(bounds, { padding: [20, 20] });
    const fitZ = m.getZoom();
    m.attributionControl
      .setPrefix('')
      .addAttribution(
        p.meta.data_mode === 'NASA_PDS'
          ? 'Terrain: NASA MGS MOLA MEGDR via PDS Geosciences Node · simple-cylindrical display'
          : 'Terrain: SYNTHETIC TEST FIXTURE (not NASA data) · surface = computed shaded relief · simple-cylindrical display',
      );
    ['grat', 'paths', 'routes', 'targets', 'ends', 'hover'].forEach((k) => (g.current[k] = L.layerGroup().addTo(m)));
    // graticule every 0.1°
    for (let la = Math.ceil(b.lat_min * 10) / 10; la <= b.lat_max; la += 0.1) {
      L.polyline(
        [
          [la, b.lon_min],
          [la, b.lon_max],
        ],
        { color: '#ece6dc', weight: 1, opacity: 0.12, interactive: false },
      ).addTo(g.current.grat);
      L.marker([la, b.lon_min], {
        icon: L.divIcon({ className: 'glbl', html: `${la.toFixed(1)}°N`, iconAnchor: [-4, 6] }),
        interactive: false,
      }).addTo(g.current.grat);
    }
    for (let lo = Math.ceil(b.lon_min * 10) / 10; lo <= b.lon_max; lo += 0.1) {
      L.polyline(
        [
          [b.lat_min, lo],
          [b.lat_max, lo],
        ],
        { color: '#ece6dc', weight: 1, opacity: 0.12, interactive: false },
      ).addTo(g.current.grat);
      L.marker([b.lat_max, lo], {
        icon: L.divIcon({ className: 'glbl', html: `${lo.toFixed(1)}°E`, iconAnchor: [-3, -4] }),
        interactive: false,
      }).addTo(g.current.grat);
    }
    const upd = () => {
      const z = m.getZoom();
      const degPerPx = 1 / Math.pow(2, z);
      const kmPerPx = degPerPx * 59.27;
      const km = [1, 2, 5, 10, 20].find((k) => k / kmPerPx > 70) || 20;
      setScale({ px: km / kmPerPx, km });
    };
    const lad = () => {
      const z = m.getZoom() - fitZ;
      cb.current.onScale?.(z < 0.6 ? 1 : z < 1.8 ? 2 : 3);
    };
    m.on('zoomend', upd);
    m.on('zoomend', lad);
    upd();
    lad();
    m.on('mousemove', (e: L.LeafletMouseEvent) =>
      setRead((r) => (r.startsWith('CELL') ? r : `${e.latlng.lat.toFixed(4)}°N  ${e.latlng.lng.toFixed(4)}°E`)),
    );
    m.on('click', async (e: L.LeafletMouseEvent) => {
      const c = cb.current;
      const pt = { lat: +e.latlng.lat.toFixed(4), lon: +e.latlng.lng.toFixed(4) };
      if (c.picking) {
        c.onPick(c.picking, pt);
        return;
      }
      try {
        const v = await api<any>(`/api/cell?lat=${pt.lat}&lon=${pt.lon}`);
        setRead(
          `CELL ${v.lat}°N ${v.lon}°E · elev ${v.elev_m} m · slope ${v.slope_deg}° · relief ${v.relief_m} m · T ${v.T}` +
            (v.mola_shots != null ? ` · MOLA shots ${v.mola_shots}${v.interpolated ? ' (interpolated)' : ''}` : ''),
        );
        setTimeout(() => setRead((r) => (r.startsWith('CELL') ? `${pt.lat}°N  ${pt.lon}°E` : r)), 6000);
      } catch (err: any) {
        setRead(err.message);
      }
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  // Raster layers. Layers without `smooth` are drawn pixelated so the grid cell size stays visible.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    p.layers.forEach((l, i) => {
      const on = !!p.visible[l.id];
      if (on && !imgs.current[l.id]) {
        imgs.current[l.id] = L.imageOverlay(layerUrl(l.png), bounds, {
          className: l.smooth ? '' : 'pix',
          zIndex: 10 + i,
          opacity: l.id === 'terrain' || l.id === 'surface' ? 1 : 0.85,
        }).addTo(m);
      } else if (!on && imgs.current[l.id]) {
        imgs.current[l.id].remove();
        delete imgs.current[l.id];
      }
    });
  }, [p.layers, p.visible]);

  // Perseverance path slot: real local copy (dashed white) or a SYNTHETIC illustration (dotted violet, labelled)
  useEffect(() => {
    const gg = g.current.paths;
    if (!gg) return;
    gg.clearLayers();
    p.overlays.forEach((o) => {
      if (!p.visible[o.id]) return;
      const ill = o.kind === 'illustrative';
      o.lines.forEach((ln) => {
        const ll = ln.map(([lo, la]) => [la, lo] as [number, number]);
        L.polyline(ll, {
          color: ill ? '#a99bd6' : '#ffffff',
          weight: ill ? 2.5 : 2,
          opacity: 0.9,
          dashArray: ill ? '1 7' : '8 6',
          lineCap: 'round',
        })
          .addTo(gg)
          .bindTooltip(ill ? 'Synthetic illustrative path — not rover data' : `${o.name} · local copy · display only`, {
            sticky: true,
          });
        if (ill && ll.length)
          L.marker(ll[Math.floor(ll.length / 2)], {
            icon: L.divIcon({
              className: '',
              html: '<div class="pathlab">SYNTHETIC ILLUSTRATION · NOT ROVER DATA</div>',
              iconAnchor: [-8, 22],
            }),
            interactive: false,
          }).addTo(gg);
      });
    });
  }, [p.overlays, p.visible]);

  // targets
  useEffect(() => {
    const gg = g.current.targets;
    if (!gg) return;
    gg.clearLayers();
    p.targets.forEach((t) => {
      if (t.role === 'start') return;
      const cls = t.role === 'context' ? 'ctx' : t.science ? 'sci' : '';
      const mk = L.marker([t.lat, t.lon], {
        icon: L.divIcon({
          className: '',
          html: `<div class="tmark ${cls}"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
      }).addTo(gg);
      if (t.role !== 'context')
        L.marker([t.lat, t.lon], {
          icon: L.divIcon({
            className: '',
            html: `<div class="tlab">${t.science ? 'CANDIDATE SCIENCE STOP · ' : ''}${t.name}</div>`,
            iconAnchor: [-12, 26],
          }),
          interactive: false,
        }).addTo(gg);
      mk.on('click', () => cb.current.onTarget(t));
    });
  }, [p.targets]);

  // start / destination
  useEffect(() => {
    const gg = g.current.ends;
    if (!gg) return;
    gg.clearLayers();
    L.marker([p.start.lat, p.start.lon], {
      icon: L.divIcon({
        className: '',
        html: '<div class="tmark start"></div>',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      }),
    })
      .addTo(gg)
      .bindTooltip(`START · ${p.start.name || 'custom'}`, { direction: 'bottom', className: 'tlab' });
    L.circleMarker([p.dest.lat, p.dest.lon], { radius: 13, color: '#74d6d2', weight: 1.5, fill: false })
      .addTo(gg)
      .bindTooltip(`DESTINATION · ${p.dest.name || 'custom'}`, { direction: 'top' });
  }, [p.start, p.dest]);

  // routes
  useEffect(() => {
    const gg = g.current.routes;
    if (!gg) return;
    gg.clearLayers();
    const order = [...p.routes].sort((a) => (a.route_id === p.selRoute ? 1 : -1));
    order.forEach((r) => {
      const ll = r.geojson.geometry.coordinates.map(([lo, la]) => [la, lo] as [number, number]);
      const sel = r.route_id === p.selRoute;
      const col = MODE_COLOR[r.mode];
      if (!sel) {
        const pl = L.polyline(ll, {
          color: col,
          weight: 3,
          opacity: p.selRoute ? 0.38 : 0.85,
          dashArray: p.selRoute ? '3 7' : undefined,
        }).addTo(gg);
        pl.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          cb.current.onRoute(r.route_id);
        });
        pl.on('mouseover', () => pl.setStyle({ opacity: 1, weight: 5 }));
        pl.on('mouseout', () => pl.setStyle({ opacity: p.selRoute ? 0.38 : 0.85, weight: 3 }));
        pl.bindTooltip(`${r.mode_label} · ${r.metrics.length_km} km — click to inspect`, { sticky: true });
        return;
      }
      L.polyline(ll, { color: '#080707', weight: 10, opacity: 0.6, interactive: false }).addTo(gg);
      r.stops.forEach((st) => {
        const t = p.targets.find((x) => x.id === st.target_id);
        if (!t) return;
        L.marker([t.lat, t.lon], {
          icon: L.divIcon({ className: '', html: `<div class="stopbadge">${st.number}</div>`, iconAnchor: [-10, 30] }),
          interactive: false,
        }).addTo(gg);
      });
      r.segments.forEach((s) => {
        const sl = s.coords.map(([lo, la]) => [la, lo] as [number, number]);
        const on = s.id === p.selSeg;
        const pl = L.polyline(sl, {
          color: on ? '#ffffff' : col,
          weight: on ? 7 : 4.5,
          opacity: 1,
          dashArray: s.higher_cost && !on ? '10 5' : undefined,
        }).addTo(gg);
        pl.bindTooltip(`${s.id} · ${s.higher_cost ? 'higher' : 'lower'} modeled traversal cost · click for WHY?`, {
          sticky: true,
        });
        pl.on('mouseover', () => !on && pl.setStyle({ weight: 7 }));
        pl.on('mouseout', () => !on && pl.setStyle({ weight: 4.5 }));
        pl.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          cb.current.onSeg(s.id);
        });
      });
    });
  }, [p.routes, p.selRoute, p.selSeg, p.targets]);

  // frame the computed routes when a new set arrives
  const fitted = useRef('');
  useEffect(() => {
    const m = map.current;
    if (!m || !p.routes.length) return;
    const key = p.routes.map((r) => r.route_id).join();
    if (fitted.current === key) return;
    fitted.current = key;
    const all = p.routes.flatMap((r) => r.geojson.geometry.coordinates.map(([lo, la]) => [la, lo] as [number, number]));
    m.flyToBounds(L.latLngBounds(all).pad(0.35), { duration: 0.8, maxZoom: 12 });
  }, [p.routes]);

  useEffect(() => {
    const gg = g.current.hover;
    if (!gg) return;
    gg.clearLayers();
    if (p.hover)
      L.circleMarker([p.hover.lat, p.hover.lon], {
        radius: 7,
        color: '#fff',
        weight: 2,
        fillColor: '#74d6d2',
        fillOpacity: 1,
      }).addTo(gg);
  }, [p.hover]);

  useEffect(() => {
    if (map.current) map.current.getContainer().style.cursor = p.picking ? 'crosshair' : '';
  }, [p.picking]);

  return (
    <>
      <div id="map" ref={el} />
      <div className="readout">{p.picking ? `CLICK MAP TO SET ${p.picking.toUpperCase()}` : read}</div>
      <div className="scalebar">
        {scale.km} km
        <i style={{ width: scale.px }} />
      </div>
    </>
  );
}
