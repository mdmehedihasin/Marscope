import type { Brief, Layer, Meta, Provenance, Sources, Target } from '../types';
import { Chip, STATUS_HELP } from './Panels';

function Strip({ st, letter }: { st: any; letter: string }) {
  const H = 560,
    top = 22,
    y = (km: number) => top + H - (km / st.length_km) * H;
  const ev = st.elev.map((e: number[]) => e[1]),
    mn = Math.min(...ev),
    mx = Math.max(...ev),
    sp = mx - mn || 1;
  const prof = st.elev
    .map(
      (e: number[], i: number) => `${i ? 'L' : 'M'}${(96 - ((e[1] - mn) / sp) * 70).toFixed(1)} ${y(e[0]).toFixed(1)}`,
    )
    .join('');
  return (
    <svg viewBox={`0 0 250 ${H + 50}`} className="strip">
      <path d={`${prof}L96 ${y(st.length_km)}L96 ${y(0)}Z`} className="sp-fill" />
      <path d={prof} className="sp-prof" />
      <line x1={110} x2={110} y1={y(0)} y2={y(st.length_km)} className="sp-line" />
      {st.segments.map((s: any) => (
        <g key={s.id}>
          {s.higher_cost && <line x1={110} x2={110} y1={y(s.from_km)} y2={y(s.to_km)} className="sp-hi" />}
          <line x1={102} x2={118} y1={y(s.from_km)} y2={y(s.from_km)} className="sp-tick" />
          <text x={124} y={(y(s.from_km) + y(s.to_km)) / 2 + 4} className={`sp-t ${s.higher_cost ? 'hi' : ''}`}>
            {s.id}
          </text>
        </g>
      ))}
      {st.stops.map((s: any) => (
        <g key={s.label}>
          <path d={`M110 ${y(s.at_km) - 8}l8 8l-8 8l-8 -8z`} className="sp-stop" />
          <text x={172} y={y(s.at_km) + 4} className="sp-t stop">
            {s.label.replace('SCIENCE ', '')}
          </text>
        </g>
      ))}
      <circle cx={110} cy={y(0)} r={6} className="sp-start" />
      <path d={`M110 ${y(st.length_km) - 9}l9 9l-9 9l-9 -9z`} className="sp-dest" />
      <text x={4} y={H + 46} className="sp-t">
        ROUTE {letter} · {st.length_km} km · elevation (left)
      </text>
    </svg>
  );
}

export function BriefDoc({ b, onClose }: { b: Brief; onClose: () => void }) {
  const m = b.mission,
    r = b.route;
  const St = ({ s }: { s: string }) => <Chip s={s} />;
  return (
    <div className="modal" onClick={onClose}>
      <div className="briefwrap" onClick={(e) => e.stopPropagation()}>
        <div className="noprint bactions">
          <button className="hbtn" onClick={() => window.print()}>
            PRINT / SAVE AS PDF
          </button>
          <button className="hbtn" onClick={onClose}>
            CLOSE
          </button>
        </div>
        <div className="doc">
          <div className="d-head">
            <div className="d-k">
              MARSCOPE · {b.doc_id} · GENERATED {b.generated}
            </div>
            <h1>CREW ROUTE BRIEF</h1>
            <div className="d-cls">{b.classification}</div>
          </div>
          <div className="d-body">
            <div className="d-strip">
              <Strip st={r.strip} letter={b.letter} />
            </div>
            <div className="d-grid">
              <div className="d-sec">
                <h4>
                  <em>01</em>MISSION
                </h4>
                <div className="kv">
                  <span>REGION</span>
                  <span>{m.region}</span>
                  <span>START</span>
                  <span>
                    {m.start.name || 'custom'} · {m.start.lat.toFixed(4)}°N {m.start.lon.toFixed(4)}°E
                  </span>
                  <span>DESTINATION</span>
                  <span>
                    {m.destination.name || 'custom'} · {m.destination.lat.toFixed(4)}°N {m.destination.lon.toFixed(4)}°E
                  </span>
                  <span>PRIORITY</span>
                  <span>
                    {m.route} · {m.mode} — {m.objective}
                  </span>
                </div>
              </div>
              <div className="d-sec">
                <h4>
                  <em>02</em>ROUTE
                </h4>
                <div className="kv">
                  <span>LENGTH</span>
                  <span>
                    {r.length_km} km · {r.segments} segments
                  </span>
                  {r.grid && (
                    <>
                      <span>GRID</span>
                      <span>{r.grid}</span>
                    </>
                  )}
                  <span>ELEVATION</span>
                  <span>
                    +{r.elev_gain_m} m / −{r.elev_loss_m} m
                  </span>
                  <span>SLOPE (ROUTE GRID)</span>
                  <span>
                    mean {r.slope_mean_deg}° · max {r.slope_max_deg}°
                  </span>
                </div>
                {r.alternatives.length > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th>ALTERNATIVE</th>
                        <th>KM</th>
                        <th>MAX SLOPE</th>
                        <th>STOPS</th>
                        <th>HIGHER-COST</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.alternatives.map((a: any) => (
                        <tr key={a.mode}>
                          <td>
                            ROUTE {a.letter} · {a.mode}
                          </td>
                          <td>{a.length_km}</td>
                          <td>{a.slope_max_deg}°</td>
                          <td>{a.candidate_stops}</td>
                          <td>{a.higher_cost_segments}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              <div className="d-sec">
                <h4>
                  <em>03</em>WATCH · TERRAIN
                </h4>
                {b.watch.length ? (
                  <ul>
                    {b.watch.map((w: any) => (
                      <li key={w.id}>
                        <b>{w.id}</b> (km {w.km[0]}–{w.km[1]}) — {w.note}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No segment exceeds the higher-cost threshold under this priority.</p>
                )}
              </div>
              <div className="d-sec">
                <h4>
                  <em>04</em>DISCOVER · SCIENCE
                </h4>
                {b.discover.length ? (
                  b.discover.map((s: any) => (
                    <div key={s.target_id} className="d-stop">
                      <b>{s.label}</b> · {s.name} · km {s.at_km} · {s.distance_m} m from path <St s={s.status} />
                      <div>{s.why}</div>
                      <div>
                        <i>Investigate:</i> {s.investigate}
                      </div>
                    </div>
                  ))
                ) : (
                  <p>No candidate science target within the stop radius.</p>
                )}
              </div>
              <div className="d-sec">
                <h4>
                  <em>05</em>CONDITIONS
                </h4>
                <table>
                  <tbody>
                    {b.conditions.map((c: any) => (
                      <tr key={c.item}>
                        <td>{c.item}</td>
                        <td>{c.text}</td>
                        <td>
                          <St s={c.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="d-sec">
                <h4>
                  <em>06</em>EVIDENCE · METHOD
                </h4>
                <table>
                  <tbody>
                    {b.evidence.map((e: any) => (
                      <tr key={e.name}>
                        <td>{e.name}</td>
                        <td>
                          <St s={e.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ul>
                  {b.method.map((x: string) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
              <div className="d-sec">
                <h4>
                  <em>07</em>UNCERTAINTY · LIMITATIONS
                </h4>
                <ul>
                  {b.uncertainty.map((x: string) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
              <div className="d-sec">
                <h4>
                  <em>08</em>SOURCES
                </h4>
                <ul>
                  {b.sources.map((s: any) => (
                    <li key={s.name}>
                      <b>{s.name}</b>
                      {s.archive ? ` — ${s.archive}` : ''}
                      {s.url ? <span className="mono small"> · {s.url}</span> : null}
                      {s.credit ? ` · Credit: ${s.credit}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
          <div className="d-foot">
            DON’T JUST MAP MARS. PLAN THE WALK. · MARSCOPE · TEAM DELTAX · PRE-EVENT CONCEPT PROTOTYPE, NOT WORK
            PRODUCED DURING THE OFFICIAL HACKATHON (NOV 14–15, 2026)
          </div>
        </div>
      </div>
    </div>
  );
}

const rows: [string, string][] = [
  ['source_name', 'Source'],
  ['mission', 'Mission'],
  ['instrument', 'Instrument'],
  ['product', 'Product'],
  ['archive', 'Archive'],
  ['source_url', 'Source URL'],
  ['spatial_reference', 'Spatial reference'],
  ['resolution', 'Resolution'],
  ['retrieval_date', 'Retrieved'],
  ['credit', 'Credit'],
  ['notes', 'Notes'],
];

function ProvCard({ name, p, on }: { name: string; p: Provenance; on?: boolean }) {
  return (
    <div className="pcard" style={on ? { borderColor: 'var(--cyan)' } : {}}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <b>{name}</b>
        <Chip s={p.status} />
      </div>
      <table>
        <tbody>
          {rows.map(([k, lab]) => (
            <tr key={k}>
              <td>{lab}</td>
              <td>
                {k === 'source_url' && String(p[k as keyof typeof p]).startsWith('http') ? (
                  <span>
                    <a href={p.source_url} target="_blank" rel="noreferrer">
                      {p.source_url}
                    </a>{' '}
                    <span className="k" style={{ textTransform: 'none' }}>
                      (reference only — this build did not download it)
                    </span>
                  </span>
                ) : (
                  String(p[k as keyof typeof p])
                )}
              </td>
            </tr>
          ))}
          <tr>
            <td>Processing</td>
            <td>
              <ol style={{ paddingLeft: 16 }}>
                {p.processing_steps.map((s: any, i) => (
                  <li key={i}>
                    {typeof s === 'string'
                      ? s
                      : `${s.step}: ${s.note || s.validation || ''}${s.rows ? ` rows ${s.rows.join('–')}, cols ${s.cols.join('–')}, resampled: ${s.resampled}` : ''}${s.bytes ? ` (${s.file}, ${s.bytes} bytes, ${s.lines}×${s.samples})` : ''}`}
                  </li>
                ))}
              </ol>
            </td>
          </tr>
          <tr>
            <td>Limitations</td>
            <td>
              <ul style={{ paddingLeft: 16 }}>
                {p.limitations.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function SourcesDoc({
  layers,
  targets,
  meta,
  focus,
  sources,
  onClose,
}: {
  layers: Layer[];
  targets: Target[];
  meta: Meta;
  focus?: string;
  sources: Sources | null;
  onClose: () => void;
}) {
  const ls = focus ? [...layers].sort((a) => (a.id === focus ? -1 : 1)) : layers;
  return (
    <div className="modal" onClick={onClose}>
      <div className="mbox" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose}>
          CLOSE
        </button>
        <div className="k">PROVENANCE</div>
        <h2>DATA SOURCES</h2>
        {ls.map((l) => (
          <ProvCard key={l.id} name={l.name} p={l.provenance} on={l.id === focus} />
        ))}
        {(sources?.grids || []).map((g) => (
          <ProvCard key={g.id} name={g.source_name} p={g} />
        ))}
        {(sources?.overlays || []).map((o) => (
          <ProvCard key={o.id} name={o.source_name} p={o} />
        ))}
        <div className="pcard">
          <b>Candidate targets</b>
          <table>
            <tbody>
              {targets.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>
                    <Chip s={t.status} /> {t.source}{' '}
                    {t.source_url && (
                      <a href={t.source_url} target="_blank" rel="noreferrer">
                        link
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pcard">
          <b>Not integrated in this build</b>
          <table>
            <tbody>
              {meta.unavailable.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>
                    <Chip s={u.status} /> {u.plan}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sources?.inventory && (
          <div className="pcard">
            <b>Local source files checked (offline — nothing downloaded)</b>
            <table>
              <tbody>
                {sources.inventory.map((e) => (
                  <tr key={e.id}>
                    <td>{e.present ? 'PRESENT' : 'missing'}</td>
                    <td>
                      <b>{e.name}</b>
                      <br />
                      <span className="mono small">{e.expected.join(' · ')}</span>
                      <br />
                      {e.integration}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function CreditsDoc({ meta, sources, onClose }: { meta: Meta; sources: Sources | null; onClose: () => void }) {
  return (
    <div className="modal" onClick={onClose}>
      <div className="mbox" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose}>
          CLOSE
        </button>
        <div className="k">ATTRIBUTION · LICENCES</div>
        <h2>CREDITS</h2>
        <p className="p" style={{ marginBottom: 8 }}>
          {meta.disclosure}
        </p>
        <p className="p">
          OFFLINE BUILD: this version uses only files inside the project; nothing is downloaded. Links are references
          for a future manual download. “Used in this build” says whether data from that source is actually inside this
          version.
        </p>
        <table className="ptable" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>SOURCE</th>
              <th>USED IN THIS BUILD</th>
              <th>CREDIT</th>
              <th>LICENCE / TERMS</th>
            </tr>
          </thead>
          <tbody>
            {(sources?.credits || []).map((c) => (
              <tr key={c.source}>
                <td style={{ color: 'var(--off)', fontFamily: 'var(--ui)', fontSize: 12.5 }}>{c.source}</td>
                <td>
                  {c.used ? (
                    <span className="chip DERIVED">YES</span>
                  ) : (
                    <span className="chip DATA_UNAVAILABLE">NO</span>
                  )}
                </td>
                <td>{c.credit}</td>
                <td>{c.licence}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="k" style={{ marginTop: 12, lineHeight: 1.7, textTransform: 'none', letterSpacing: '.02em' }}>
          MARSCOPE code: MIT licence (see LICENSE). NASA/USGS data keep their credit lines; third-party products keep
          their authors' credit and terms.
        </div>
      </div>
    </div>
  );
}

export function GlobeDoc({ meta, onClose }: { meta: Meta; onClose: () => void }) {
  // Orthographic projection centred on the region. Graticule + region box only: no surface data of any kind.
  const b = meta.region.bounds,
    lat0 = (b.lat_min + b.lat_max) / 2,
    lon0 = (b.lon_min + b.lon_max) / 2,
    Rr = 150,
    cx = 180,
    cy = 180,
    rad = Math.PI / 180;
  const proj = (la: number, lo: number): [number, number] | null => {
    const c =
      Math.sin(lat0 * rad) * Math.sin(la * rad) +
      Math.cos(lat0 * rad) * Math.cos(la * rad) * Math.cos((lo - lon0) * rad);
    if (c < 0) return null;
    return [
      cx + Rr * Math.cos(la * rad) * Math.sin((lo - lon0) * rad),
      cy -
        Rr *
          (Math.cos(lat0 * rad) * Math.sin(la * rad) -
            Math.sin(lat0 * rad) * Math.cos(la * rad) * Math.cos((lo - lon0) * rad)),
    ];
  };
  const line = (pts: [number, number][]) => {
    let d = '',
      pen = false;
    pts.forEach(([la, lo]) => {
      const q = proj(la, lo);
      if (!q) {
        pen = false;
        return;
      }
      d += `${pen ? 'L' : 'M'}${q[0].toFixed(1)} ${q[1].toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const grat: string[] = [];
  for (let la = -60; la <= 60; la += 30)
    grat.push(line(Array.from({ length: 181 }, (_, i) => [la, -180 + i * 2] as [number, number])));
  for (let lo = -180; lo < 180; lo += 30)
    grat.push(line(Array.from({ length: 91 }, (_, i) => [-90 + i * 2, lo] as [number, number])));
  const box = line([
    [b.lat_min, b.lon_min],
    [b.lat_min, b.lon_max],
    [b.lat_max, b.lon_max],
    [b.lat_max, b.lon_min],
    [b.lat_min, b.lon_min],
  ]);
  const c = proj(lat0, lon0)!;
  return (
    <div className="modal" onClick={onClose}>
      <div className="mbox" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose}>
          CLOSE
        </button>
        <div className="k">SCALE · GLOBAL</div>
        <h2>
          GLOBAL CONTEXT <Chip s="CONCEPTUAL" />
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 24, alignItems: 'center' }}>
          <svg
            viewBox="0 0 360 360"
            className="globe"
            role="img"
            aria-label="Schematic globe with a latitude/longitude grid and the region location"
          >
            <circle cx={cx} cy={cy} r={Rr} className="g-limb" />
            {grat.map((d, i) => (
              <path key={i} d={d} className="g-grat" />
            ))}
            <path d={box} className="g-box" />
            <circle cx={c[0]} cy={c[1]} r={4} className="g-dot" />
            <text x={c[0] + 10} y={c[1] - 8} className="g-t">
              {meta.region.name.toUpperCase()}
            </text>
            <text x={cx} y={348} className="g-t mid">
              SCHEMATIC — NOT A NASA BASEMAP
            </text>
          </svg>
          <div>
            <p className="p">
              This is a <b>schematic</b>: a latitude/longitude grid drawn on a sphere, with the region box at{' '}
              {lat0.toFixed(2)}°N {lon0.toFixed(2)}°E. It shows <b>no surface data</b>.
            </p>
            <p className="p" style={{ marginTop: 8 }}>
              No local global basemap is in this build, and online tiles (e.g. Mars Trek) are not used in offline mode.
              A real global view is planned work.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LimitsDoc({ meta, onClose }: { meta: Meta; onClose: () => void }) {
  const a = meta.assumptions,
    t = a.terrain,
    s = meta.stats;
  const groups: [string, string[]][] = [
    [
      'Data mode',
      [
        meta.data_mode === 'NASA_PDS'
          ? 'Terrain values come from the official MOLA MEGDR tile (unchanged), clipped to the region.'
          : 'SYNTHETIC TEST FIXTURE: terrain values are NOT NASA data. This offline build cannot download. On a machine with internet, run scripts/fetch_mola.py + scripts/build_region.py to load real MOLA.',
      ],
    ],
    ['Unavailable layers', meta.unavailable.map((u) => `${u.name} — ${u.status.replace('_', ' ')}`)],
    [
      'Missing coverage',
      [
        s.interpolated_fraction == null
          ? 'Shot-count layer not loaded.'
          : meta.data_mode === 'NASA_PDS'
            ? `${Math.round((s.interpolated_fraction as number) * 100)}% of MOLA bins in this region contain zero laser shots (interpolated). Toggle "MOLA coverage" to see them.`
            : `${Math.round((s.interpolated_fraction as number) * 100)}% of bins in the SYNTHETIC shot-count grid have zero shots (generated gaps, not real MOLA coverage). Toggle "Shot-count coverage" to see them.`,
      ],
    ],
    [
      'Different resolutions',
      [
        'Source grid: 1/128° (~463 m N-S). Routes are searched on a 1/512° (~116 m) grid and slope evidence is read on a 1/1024° (~58 m) grid. Both are cubic interpolations: finer spacing does NOT add terrain information.',
        ...Object.entries(meta.slope_by_level || {}).map(
          ([k, v]) =>
            `Slope on the ${k} grid (${v.cell_deg}): mean ${v.mean_deg}°, p95 ${v.p95_deg}°, max ${v.max_deg}°, ${v.cells_above_limit} cells above ${t.max_slope_deg}°.`,
        ),
        'Slope numbers change with grid spacing: a longer baseline averages steep steps away; splines can also overshoot at sharp breaks. Compare slopes only at the same spacing.',
      ],
    ],
    [
      'Preprocessing assumptions',
      [
        `Slope by central differences (two cells apart: ~926 m baselines on the native grid, ~232 m on the routing grid); local relief = max−min in a ~1.4 km window.`,
        `Hillshade and the SURFACE shaded relief use 3× vertical exaggeration (display only, never used in analysis).`,
      ],
    ],
    [
      'Spatial uncertainty',
      [
        'MOLA shot locations are known to ~100 m; the grid cell is ~463 m. Target positions marked APPROXIMATE are placements, not surveyed points.',
      ],
    ],
    [
      'Route-model assumptions',
      [
        `T = ${t.w_slope}·min(1, slope/${t.slope_ref_deg}°)² + ${t.w_relief}·min(1, relief/${t.relief_ref_m} m)`,
        `Cells steeper than ${t.max_slope_deg}° are excluded (${s.excluded_cells} cells here). This is a modelling threshold, NOT a human mobility limit.`,
        `Science proximity σ = ${a.science_sigma_m} m.`,
        ...Object.values(a.modes).map((m) => `${m.label}: α=${m.alpha}, β=${m.beta}, γ=${m.gamma}`),
      ],
    ],
    [
      'Unsupported conclusions',
      [
        'MARSCOPE does not label any route safe or unsafe.',
        'No mineral detections are claimed; no CRISM data is in this build.',
        'The dotted violet line is a SYNTHETIC illustration, not the Perseverance path.',
        'The SURFACE layer is computed shaded relief, not orbital imagery.',
      ],
    ],
    [
      'Temporal information',
      [
        'MOLA data were acquired 1999–2001 (the synthetic fixture has no epoch). No MEDA files were provided: no dust, weather, lighting or seasonal conditions are shown or modeled.',
      ],
    ],
  ];
  return (
    <div className="modal" onClick={onClose}>
      <div className="mbox" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose}>
          CLOSE
        </button>
        <div className="k">SCIENTIFIC HONESTY IS PART OF THE PRODUCT</div>
        <h2>DATA LIMITATIONS</h2>
        {groups.map(([g, items]) => (
          <div className="pcard" key={g}>
            <b>{g}</b>
            <ul style={{ paddingLeft: 18, marginTop: 6 }}>
              {items.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        ))}
        <div className="pcard">
          <b>Status vocabulary used in the interface</b>
          <table>
            <tbody>
              {Object.entries(meta.status_vocabulary).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    <Chip s={k} />
                  </td>
                  <td>
                    {v}
                    <br />
                    <span className="k" style={{ textTransform: 'none' }}>
                      {STATUS_HELP.find(([s]) => s === k)?.[1]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function SystemDoc({ meta, onClose }: { meta: Meta; onClose: () => void }) {
  const n = meta.pipeline.length,
    x = (i: number) => 60 + i * (880 / (n - 1));
  let d = '';
  for (let px = 60; px <= 940; px += 5)
    d += `${d ? 'L' : 'M'}${px} ${60 + 12 * Math.sin(((px - 60) / (880 / (n - 1))) * Math.PI)}`;
  return (
    <div className="modal" onClick={onClose}>
      <div className="mbox wide" onClick={(e) => e.stopPropagation()}>
        <button className="x" onClick={onClose}>
          CLOSE
        </button>
        <div className="kick">ARCHITECTURE · STATUS OF THIS PRE-EVENT BUILD</div>
        <h2>FROM ORBIT TO ONE PAGE</h2>
        <svg viewBox="0 0 1000 150" className="pipe-svg">
          <path d={d} className="pp-line" />
          {meta.pipeline.map((p, i) => (
            <g key={p.stage}>
              <circle cx={x(i)} cy={60} r={8} className={`pp-dot ${p.status}`} />
              {(() => {
                const w = p.stage.split(' ');
                const h = Math.ceil(w.length / 2);
                return [w.slice(0, h).join(' '), w.slice(h).join(' ')];
              })().map((t, k) => (
                <text key={k} x={x(i)} y={96 + k * 16} className="pp-t">
                  {t}
                </text>
              ))}
              <text x={x(i)} y={136} className="pp-s">
                {String(i + 1).padStart(2, '0')}
              </text>
            </g>
          ))}
        </svg>
        <table className="ptable">
          <thead>
            <tr>
              <th>#</th>
              <th>STAGE</th>
              <th>STATUS</th>
              <th>IN THIS BUILD</th>
              <th>NEXT (HACKATHON)</th>
            </tr>
          </thead>
          <tbody>
            {meta.pipeline.map((p, i) => (
              <tr key={p.stage}>
                <td>{String(i + 1).padStart(2, '0')}</td>
                <td>
                  <b>{p.stage}</b>
                </td>
                <td>
                  <span className={`chip ${p.status === 'IMPLEMENTED' ? 'DERIVED' : 'CONCEPTUAL'}`}>{p.status}</span>
                </td>
                <td>{p.built}</td>
                <td>{p.next}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="k" style={{ marginTop: 12, lineHeight: 1.6 }}>
          Data in use:{' '}
          {meta.data_mode === 'NASA_PDS'
            ? 'official MOLA MEGDR (PDS)'
            : 'SYNTHETIC TEST FIXTURE — load real MOLA with scripts/fetch_mola.py on a machine with internet'}
          . {meta.disclosure}
        </div>
      </div>
    </div>
  );
}
