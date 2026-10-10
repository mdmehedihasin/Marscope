import { useRef } from 'react';
import type { ProfilePt, Route } from '../types';

const W = 1000,
  H = 160;
const tracks = [
  { k: 'elev_m', y0: 4, y1: 58, lab: 'ELEVATION', col: '#d8b98e' },
  { k: 'slope_deg', y0: 66, y1: 100, lab: 'SLOPE', col: '#e0a84a' },
  { k: 'T', y0: 108, y1: 136, lab: 'TERRAIN COST', col: '#d0703f' },
] as const;

export default function Profile({
  route,
  selSeg,
  onSeg,
  onHover,
  color,
}: {
  route: Route;
  selSeg: string | null;
  onSeg: (id: string) => void;
  onHover: (p: ProfilePt | null) => void;
  color: string;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const pr = route.profile;
  const L = pr[pr.length - 1].d_km || 1;
  const x = (d: number) => (d / L) * W;
  const path = (k: 'elev_m' | 'slope_deg' | 'T', y0: number, y1: number) => {
    const v = pr.map((p) => p[k] as number);
    const mn = Math.min(...v),
      mx = Math.max(...v) || 1;
    const sp = mx - mn || 1;
    return {
      d: pr
        .map(
          (p, i) =>
            `${i ? 'L' : 'M'}${x(p.d_km).toFixed(1)} ${(y1 - (((p[k] as number) - mn) / sp) * (y1 - y0)).toFixed(1)}`,
        )
        .join(''),
      mn,
      mx,
    };
  };
  const move = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const d = ((e.clientX - r.left) / r.width) * L;
    let best = pr[0];
    for (const p of pr) if (Math.abs(p.d_km - d) < Math.abs(best.d_km - d)) best = p;
    onHover(best);
  };
  const click = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const d = ((e.clientX - r.left) / r.width) * L;
    const s = route.segments.find((s) => pr[s.from_vertex].d_km <= d && d <= pr[s.to_vertex].d_km);
    if (s) onSeg(s.id);
  };
  return (
    <div className="prof">
      {tracks.map((t) => {
        const pp = path(t.k, t.y0, t.y1);
        return (
          <div key={t.k} className="plab" style={{ top: 10 + (t.y0 / H) * 168 }}>
            {t.lab}
            <br />
            <span style={{ color: t.col }}>
              {t.k === 'T'
                ? `${pp.mn.toFixed(2)}–${pp.mx.toFixed(2)}`
                : `${Math.round(pp.mn)}–${Math.round(pp.mx)}${t.k === 'elev_m' ? ' m' : '°'}`}
            </span>
          </div>
        );
      })}
      <div className="plab" style={{ top: 10 + (142 / H) * 168 }}>
        SCIENCE
      </div>
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        onMouseMove={move}
        onMouseLeave={() => onHover(null)}
        onClick={click}
        style={{ cursor: 'pointer' }}
      >
        {route.segments.map((s) => {
          const a = x(pr[s.from_vertex].d_km),
            b = x(pr[s.to_vertex].d_km);
          const on = s.id === selSeg;
          return (
            <g key={s.id}>
              <rect
                x={a}
                y={0}
                width={Math.max(1, b - a)}
                height={H}
                fill={on ? 'rgba(255,255,255,.10)' : s.higher_cost ? 'rgba(224,168,74,.07)' : 'transparent'}
              />
              <line x1={a} x2={a} y1={0} y2={H} stroke="rgba(236,230,220,.12)" vectorEffect="non-scaling-stroke" />
            </g>
          );
        })}
        {tracks.map((t) => (
          <path
            key={t.k}
            d={path(t.k, t.y0, t.y1).d}
            fill="none"
            stroke={t.k === 'elev_m' ? color : t.col}
            strokeWidth={1.6}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {pr
          .filter((p) => p.S > 0.35)
          .map((p, i) => (
            <circle key={i} cx={x(p.d_km)} cy={148} r={2.2 + 3 * p.S} fill="#74d6d2" opacity={0.25 + 0.6 * p.S} />
          ))}
        {route.stops.map((s) => (
          <g key={s.target_id}>
            <line
              x1={x(s.at_km)}
              x2={x(s.at_km)}
              y1={140}
              y2={156}
              stroke="#e0a84a"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        ))}
      </svg>
    </div>
  );
}
