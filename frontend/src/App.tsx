import { useEffect, useMemo, useState } from 'react';
import { api, isOffline } from './api';
import type { Brief, Diff, Evidence, Layer, Meta, Overlay, ProfilePt, Pt, Route, Sources, Target } from './types';
import MapView, { MODE_COLOR } from './components/MapView';
import Profile from './components/Profile';
import { ExplorePanel, LETTER, PlanPanel, Rail, StopPanel, WhyPanel } from './components/Panels';
import { BriefDoc, CreditsDoc, GlobeDoc, LimitsDoc, SourcesDoc, SystemDoc } from './components/Docs';

type Tab = 'explore' | 'plan' | 'why';
// Demo Mission steps: data → routes → priority → WHY → science stop → sources → brief → system.
const DEMO = [
  'Mars is one place. Its evidence is distributed — here: a terrain grid + candidate science targets.',
  'One route, many questions: three routes, each an exact least-cost path on the 1/512° grid, one per mission priority.',
  'Change what the mission values most, and the route changes with it — ROUTE B, science-first.',
  "WHY THIS SEGMENT? Don't just recommend. Show the evidence.",
  'Science along the way: a candidate science stop on the selected route.',
  'Every layer traces back to its archive record.',
  'Crew Route Brief: route · watch · discover · conditions · sources · uncertainty.',
  "From orbit to one page — the pipeline, with honest status. Don't just map Mars. Plan the walk.",
];

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [visible, setVisible] = useState<Record<string, boolean>>({ terrain: true });
  const [start, setStart] = useState<Pt | null>(null);
  const [dest, setDest] = useState<Pt | null>(null);
  const [mode, setMode] = useState('balanced');
  const [routes, setRoutes] = useState<Route[]>([]);
  const [diffs, setDiffs] = useState<Diff[]>([]);
  const [selRoute, setSelRoute] = useState<string | null>(null);
  const [selSeg, setSelSeg] = useState<string | null>(null);
  const [ev, setEv] = useState<Evidence | null>(null);
  const [stop, setStop] = useState<Target | null>(null);
  const [tab, setTab] = useState<Tab>('explore');
  const [hover, setHover] = useState<ProfilePt | null>(null);
  const [scale, setScale] = useState(1);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [modal, setModal] = useState<'' | 'sources' | 'limits' | 'system' | 'credits' | 'globe'>('');
  const [focus, setFocus] = useState<string>();
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [sources, setSources] = useState<Sources | null>(null);
  const [grid, setGrid] = useState('routing');
  const [picking, setPicking] = useState<'start' | 'dest' | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [boot, setBoot] = useState(0);
  const [intro, setIntro] = useState(true);
  const [step, setStep] = useState(-1);

  const fail = (e: any) => {
    setErr(e?.message || 'Something went wrong');
    setTimeout(() => setErr(''), 6000);
  };
  useEffect(() => {
    (async () => {
      try {
        const m = await api<Meta>('/api/metadata');
        setMeta(m);
        setBoot(1);
        const L = await api<{ layers: Layer[] }>('/api/layers');
        setLayers(L.layers);
        setBoot(2);
        const T = await api<any>('/api/science-targets');
        const ts: Target[] = T.features.map((f: any) => f.properties);
        setTargets(ts);
        setBoot(3);
        api<{ overlays: Overlay[] }>('/api/overlays')
          .then((o) => setOverlays(o.overlays || []))
          .catch(() => setOverlays([]));
        api<Sources>('/api/sources')
          .then(setSources)
          .catch(() => setSources(null));
        const s = ts.find((t) => t.role === 'start')!,
          d = ts.find((t) => t.role === 'destination')!;
        setStart({ lat: s.lat, lon: s.lon, name: s.name });
        setDest({ lat: d.lat, lon: d.lon, name: d.name });
        setBoot(4);
        setTimeout(() => setIntro(false), 1700);
      } catch (e) {
        fail(e);
      }
    })();
  }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setModal('');
        setBrief(null);
        setPicking(null);
      }
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, []);

  const selected = useMemo(() => routes.find((r) => r.route_id === selRoute) || null, [routes, selRoute]);
  const journey = brief ? 3 : (ev || stop) && tab === 'why' ? 2 : tab === 'plan' ? 1 : tab === 'why' ? 2 : 0;
  const generate = async (m = mode, gr = grid): Promise<Route[]> => {
    if (!start || !dest) return [];
    setBusy(true);
    setEv(null);
    setSelSeg(null);
    setStop(null);
    try {
      const r = await api<{ routes: Route[]; differences: Diff[] }>('/api/routes/compare', { start, dest, grid: gr });
      setRoutes(r.routes);
      setDiffs(r.differences || []);
      const s = r.routes.find((x) => x.mode === m)!;
      setSelRoute(s.route_id);
      setTab('plan');
      return r.routes;
    } catch (e) {
      fail(e);
      return [];
    } finally {
      setBusy(false);
    }
  };
  const chooseMode = (m: string) => {
    setMode(m);
    const r = routes.find((x) => x.mode === m);
    if (r) {
      setSelRoute(r.route_id);
      setSelSeg(null);
      setEv(null);
    }
  };
  const openSeg = async (id: string, rid = selRoute) => {
    if (!rid) return;
    setSelSeg(id);
    setStop(null);
    try {
      setEv(await api<Evidence>(`/api/routes/${rid}/evidence?segment=${id}`));
      setTab('why');
    } catch (e) {
      fail(e);
    }
  };
  const openBrief = async (rid = selRoute) => {
    if (!rid) {
      fail({ message: 'Generate routes first, then select one.' });
      return;
    }
    try {
      setBrief(await api<Brief>('/api/crew-brief', { route_id: rid }));
    } catch (e) {
      fail(e);
    }
  };
  const pickRoute = (id: string) => {
    setSelRoute(id);
    setSelSeg(null);
    setEv(null);
    const r = routes.find((x) => x.route_id === id);
    if (r) setMode(r.mode);
    setTab('plan');
  };
  const openTarget = (t: Target) => {
    setStop(t);
    setEv(null);
    setTab('why');
  };
  const goJourney = (i: number) => {
    if (i === 3) openBrief();
    else {
      setBrief(null);
      setTab((['explore', 'plan', 'why'] as Tab[])[i]);
    }
  };

  const demoStep = async (k: number) => {
    setStep(k);
    let rs = routes;
    if (k === 0) {
      setVisible({ terrain: true, science: true });
      const s = targets.find((t) => t.role === 'start')!,
        d = targets.find((t) => t.role === 'destination')!;
      setStart({ lat: s.lat, lon: s.lon, name: s.name });
      setDest({ lat: d.lat, lon: d.lon, name: d.name });
      setModal('');
      setBrief(null);
      setRoutes([]);
      setSelRoute(null);
      setEv(null);
      setStop(null);
      setTab('explore');
    }
    if (k === 1) {
      setMode('traversability');
      setGrid('routing');
      await generate('traversability', 'routing');
    }
    if (k === 2) chooseMode('science');
    if (k === 3) {
      rs = routes;
      const r = rs.find((x) => x.mode === 'balanced')!;
      setMode('balanced');
      setSelRoute(r.route_id);
      setVisible((v) => ({ ...v, cost: true }));
      const s = [...r.segments].sort((a, b) => b.cost_per_m - a.cost_per_m)[0];
      await openSeg(s.id, r.route_id);
    }
    if (k === 4) {
      const r = routes.find((x) => x.mode === 'balanced')!;
      const st = r.stops[0];
      const t = targets.find((x) => x.id === st?.target_id) || targets.find((x) => x.science)!;
      setVisible((v) => ({ ...v, cost: false }));
      setSelSeg(null);
      openTarget(t);
    }
    if (k === 5) {
      setFocus('terrain');
      setModal('sources');
    }
    if (k === 6) {
      setModal('');
      await openBrief(routes.find((x) => x.mode === 'balanced')?.route_id);
    }
    if (k === 7) {
      setBrief(null);
      setModal('system');
    }
  };
  const startDemo = async () => {
    await demoStep(0);
    setTimeout(() => demoStep(1), 60);
  };

  if (!meta || !start || !dest) return <Intro boot={boot} meta={meta} />;
  const synth = meta.data_mode !== 'NASA_PDS';
  const demoText = (k: number) =>
    k === 0
      ? `${DEMO[0]} ${synth ? 'In this offline build the terrain is a SYNTHETIC test fixture, not NASA data.' : 'Terrain: NASA MOLA.'}`
      : DEMO[k];
  return (
    <>
      {intro && <Intro boot={boot} meta={meta} fading />}
      <div className="app">
        <header>
          <div className="brand">MARSCOPE</div>
          <div className="brand-sub">MISSION-AWARE ROUTE INTELLIGENCE</div>
          <nav className="journey">
            {['EXPLORE', 'PLAN', 'WHY', 'BRIEF'].map((j, i) => (
              <button key={j} className={journey === i ? 'on' : ''} onClick={() => goJourney(i)}>
                {j}
              </button>
            ))}
            <i style={{ transform: `translateX(${journey * (window.innerWidth <= 1450 ? 88 : 104)}px)` }} />
          </nav>
          <div className="hgap" />
          <span className="statuschip" title={meta.disclosure}>
            <i />
            PRE-EVENT CONCEPT PROTOTYPE
          </span>
          <span className="mode-badge off offbuild" title="Uses only files inside this project; nothing is downloaded.">
            OFFLINE BUILD
          </span>
          <span className={`mode-badge ${synth ? 'synth' : 'real'}`}>
            {synth ? 'SYNTHETIC TEST TERRAIN' : 'NASA PDS · MOLA'}
          </span>
          {isOffline() && (
            <span className="mode-badge off" title="Backend not reachable — bundled snapshot">
              OFFLINE SNAPSHOT
            </span>
          )}
          <button className="hbtn demo" onClick={startDemo}>
            ▶ DEMO MISSION
          </button>
          <button className="hbtn" onClick={() => setModal('system')}>
            SYSTEM
          </button>
          <button
            className="hbtn"
            onClick={() => {
              setFocus(undefined);
              setModal('sources');
            }}
          >
            SOURCES
          </button>
          <button className="hbtn" onClick={() => setModal('limits')}>
            LIMITATIONS
          </button>
          <button className="hbtn" onClick={() => setModal('credits')}>
            CREDITS
          </button>
        </header>

        <aside className="left">
          <Rail
            layers={layers}
            overlays={overlays}
            visible={visible}
            meta={meta}
            scale={scale}
            toggle={(id) => setVisible((v) => ({ ...v, [id]: !v[id] }))}
            onSource={(l) => {
              setFocus(l.id);
              setModal('sources');
            }}
            onGlobal={() => setModal('globe')}
          />
        </aside>

        <main className="center">
          <MapView
            meta={meta}
            layers={layers}
            overlays={overlays}
            visible={visible}
            targets={targets}
            routes={routes}
            selRoute={selRoute}
            selSeg={selSeg}
            hover={hover}
            start={start}
            dest={dest}
            picking={picking}
            onScale={setScale}
            onPick={(k, p) => {
              k === 'start' ? setStart(p) : setDest(p);
              setPicking(null);
              setRoutes([]);
              setDiffs([]);
              setSelRoute(null);
              setEv(null);
            }}
            onRoute={pickRoute}
            onSeg={(id) => openSeg(id)}
            onTarget={openTarget}
          />
          {synth && (
            <div className="banner">
              SYNTHETIC TEST TERRAIN — NOT NASA DATA · offline build, pipeline demonstration only · real MOLA can be
              loaded later with scripts/fetch_mola.py (needs internet)
            </div>
          )}
          {step >= 0 && (
            <div className="stepper">
              <b>
                DEMO {step + 1}/{DEMO.length}
              </b>
              <span>{demoText(step)}</span>
              {step < DEMO.length - 1 && <button onClick={() => demoStep(step + 1)}>NEXT ›</button>}
              <button
                className="ghost"
                onClick={() => {
                  setStep(-1);
                  setModal('');
                }}
              >
                END
              </button>
            </div>
          )}
        </main>

        <aside className="right">
          {tab === 'explore' && (
            <ExplorePanel
              meta={meta}
              targets={targets}
              layers={layers}
              onTarget={openTarget}
              onSystem={() => setModal('system')}
              onSource={(l) => {
                setFocus(l.id);
                setModal('sources');
              }}
            />
          )}
          {tab === 'plan' && (
            <PlanPanel
              meta={meta}
              start={start}
              dest={dest}
              picking={picking}
              setPicking={setPicking}
              mode={mode}
              chooseMode={chooseMode}
              generate={() => generate()}
              busy={busy}
              routes={routes}
              sel={selRoute}
              onSel={pickRoute}
              diffs={diffs}
              grid={grid}
              setGrid={(gr) => {
                setGrid(gr);
                setRoutes([]);
                setDiffs([]);
                setSelRoute(null);
                setEv(null);
              }}
            />
          )}
          {tab === 'why' &&
            (ev ? (
              <WhyPanel
                ev={ev}
                route={selected}
                onSources={() => {
                  setFocus('terrain');
                  setModal('sources');
                }}
              />
            ) : stop ? (
              <StopPanel t={stop} route={selected} />
            ) : (
              <div className="empty">
                Click any segment of the selected route — or a science marker — to see the evidence chain behind it.
              </div>
            ))}
        </aside>

        <section className="bottom">
          <div className="pmeta">
            <h3>Route profile</h3>
            {selected ? (
              <>
                <div className="big" style={{ color: MODE_COLOR[selected.mode] }}>
                  ROUTE {LETTER[selected.mode]} · {selected.mode_label}
                </div>
                <div className="k">
                  {selected.metrics.length_km} km · {selected.metrics.segments} segments · +
                  {selected.metrics.elev_gain_m} m
                </div>
                <div className="k" style={{ marginTop: 8, color: 'var(--off2)' }}>
                  {hover
                    ? `km ${hover.d_km} · ${hover.elev_m} m · ${hover.slope_deg}° · T ${hover.T}${hover.interpolated ? ' · interpolated bin' : ''}`
                    : 'Hover the profile · click to open a segment'}
                </div>
              </>
            ) : (
              <div className="k" style={{ marginTop: 10 }}>
                No route selected — press ▶ DEMO MISSION or PLAN → GENERATE ROUTES
              </div>
            )}
          </div>
          {selected ? (
            <Profile
              route={selected}
              selSeg={selSeg}
              onSeg={(id) => openSeg(id)}
              onHover={setHover}
              color={MODE_COLOR[selected.mode]}
            />
          ) : (
            <div className="empty">
              Elevation, slope, modeled cost and science opportunity along the selected route appear here.
            </div>
          )}
          <div className="pact">
            <button className="bigbtn" disabled={!selected} onClick={() => openBrief()}>
              CREW ROUTE BRIEF ›
            </button>
            <div className="k" style={{ lineHeight: 1.6 }}>
              Generated only from the computed route, its evidence and source records. Printable / save as PDF.
            </div>
          </div>
        </section>
      </div>
      {err && (
        <div className="toast" role="alert">
          {err}
        </div>
      )}
      {brief && <BriefDoc b={brief} onClose={() => setBrief(null)} />}
      {modal === 'sources' && (
        <SourcesDoc
          layers={layers}
          targets={targets}
          meta={meta}
          focus={focus}
          sources={sources}
          onClose={() => setModal('')}
        />
      )}
      {modal === 'credits' && <CreditsDoc meta={meta} sources={sources} onClose={() => setModal('')} />}
      {modal === 'globe' && <GlobeDoc meta={meta} onClose={() => setModal('')} />}
      {modal === 'limits' && <LimitsDoc meta={meta} onClose={() => setModal('')} />}
      {modal === 'system' && <SystemDoc meta={meta} onClose={() => setModal('')} />}
    </>
  );
}

function Intro({ boot, meta, fading }: { boot: number; meta: Meta | null; fading?: boolean }) {
  const lines = [
    'TERRAIN · elevation grid + 1/512° routing grid',
    'LAYERS · provenance records',
    'SCIENCE · candidate targets',
    'ROUTE ENGINE · exact least-cost search, 3 priorities',
  ];
  return (
    <div className={`intro ${fading ? 'out' : ''}`}>
      <div className="k">NASA SPACE APPS CHALLENGE 2026 · INTERPLANETARY SURVIVAL GUIDE: MARTIAN MAP · TEAM DELTAX</div>
      <h1>MARSCOPE</h1>
      <div className="desc">MISSION-AWARE ROUTE INTELLIGENCE FOR MARS</div>
      <div className="tg">
        ONE ROUTE. <span>EVERY LAYER.</span> <span className="cy">ONE CREW BRIEF.</span>
      </div>
      <div className="ld">
        {lines.map((l, i) => (
          <div key={l} className={boot > i ? 'ok' : ''}>
            {boot > i ? '✓' : '·'} {l}
          </div>
        ))}
        <div className="na">· SURFACE · CTX / HiRISE imagery — unavailable offline (shaded relief only)</div>
        {meta && meta.data_mode !== 'NASA_PDS' && (
          <div className="na">· DATA MODE · SYNTHETIC test fixture — not NASA data</div>
        )}
      </div>
      <div className="disc">
        PRE-EVENT CONCEPT PROTOTYPE, NOT WORK PRODUCED DURING THE OFFICIAL HACKATHON (NOV 14–15, 2026) · OFFLINE BUILD
      </div>
      {meta && (
        <div className="ipipe">
          {meta.pipeline.map((p, i) => (
            <div key={p.stage} style={{ animationDelay: `${0.15 + i * 0.12}s` }}>
              <i />
              {p.stage}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
