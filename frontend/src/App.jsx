import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import * as THREE from "three";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  Satellite, Search, AlertTriangle, RefreshCw, Radio, Globe, Info, ChevronDown, X,
} from "lucide-react";
import { fetchObjects, API_BASE } from "./api.js";

/* ============================================================
   THEME TOKENS
   ============================================================ */
const COLORS = {
  bg: "#060A12",
  surface: "#0D1420",
  surfaceRaised: "#111B2C",
  hairline: "#1C2B42",
  textPrimary: "#E8EDF6",
  textMuted: "#7C8AA6",
  textFaint: "#4B5B78",
  teal: "#4FD1C5",
  amber: "#F5A623",
  violet: "#8B7FF0",
  rose: "#F0708B",
  regime: { LEO: "#4FD1C5", MEO: "#8B7FF0", GEO: "#F5A623", HEO: "#F0708B", UNKNOWN: "#4B5B78" },
  freshness: { CURRENT: "#4FD1C5", RECENT: "#8B7FF0", STALE: "#F5A623", UNAVAILABLE: "#4B5B78" },
};

const FONT_DISPLAY = "'Space Grotesk', 'Segoe UI', sans-serif";
const FONT_MONO = "'JetBrains Mono', 'SF Mono', Consolas, monospace";

/* ============================================================
   ORBITAL POSITION MATH (for the 3D globe only -- regime/altitude/
   period are computed by the backend; this is purely geometric)
   ============================================================ */
const EARTH_RADIUS_KM = 6378.137;

// Classical orbital elements -> position vector (km). Two-body
// approximation for visualization, not a full SGP4 propagation.
function orbitalElementsToPosition(a, e, iDeg, raanDeg, argpDeg, maDeg) {
  const i = (iDeg * Math.PI) / 180;
  const raan = (raanDeg * Math.PI) / 180;
  const argp = (argpDeg * Math.PI) / 180;
  let M = (maDeg * Math.PI) / 180;

  let E = M;
  for (let k = 0; k < 8; k++) {
    E = E - (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  }
  const nu = 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2));
  const r = a * (1 - e * Math.cos(E));

  const xPf = r * Math.cos(nu);
  const yPf = r * Math.sin(nu);

  const cosO = Math.cos(raan), sinO = Math.sin(raan);
  const cosW = Math.cos(argp), sinW = Math.sin(argp);
  const cosI = Math.cos(i), sinI = Math.sin(i);

  const x = (cosO * cosW - sinO * sinW * cosI) * xPf + (-cosO * sinW - sinO * cosW * cosI) * yPf;
  const y = (sinO * cosW + cosO * sinW * cosI) * xPf + (-sinO * sinW + cosO * cosW * cosI) * yPf;
  const z = (sinW * sinI) * xPf + (cosW * sinI) * yPf;

  return { x, y, z };
}

/* ============================================================
   LOCAL FALLBACK NORMALIZATION
   Only used if the backend API is unreachable (e.g. not started
   yet). Mirrors the backend's normalize.py so the UI has a
   consistent shape either way -- always tagged UNAVAILABLE, never
   presented as if it came from the real ingestion pipeline.
   ============================================================ */
const LEO_MAX_ALT_KM = 2000;
const MEO_MAX_ALT_KM = 35586;
const GEO_BAND_KM = [35586, 35986];
const EARTH_MU = 398600.4418;

function deriveOrbitLocal(meanMotion, eccentricity) {
  if (!meanMotion || meanMotion <= 0) return null;
  const n = (meanMotion * 2 * Math.PI) / 86400;
  const a = Math.cbrt(EARTH_MU / (n * n));
  const e = eccentricity ?? 0;
  const apogee = a * (1 + e) - EARTH_RADIUS_KM;
  const perigee = a * (1 - e) - EARTH_RADIUS_KM;
  const periodMin = 1440 / meanMotion;

  // Classify by APOGEE, not mean altitude -- a highly-elliptical (HEO)
  // orbit can have a low perigee that would otherwise drag a mean-based
  // classification down into MEO/LEO range.
  let regime = "UNKNOWN";
  if (apogee <= LEO_MAX_ALT_KM) regime = "LEO";
  else if (apogee >= GEO_BAND_KM[0] && apogee <= GEO_BAND_KM[1] && e < 0.05) regime = "GEO";
  else if (apogee <= MEO_MAX_ALT_KM) regime = "MEO";
  else regime = "HEO";

  return { semiMajorAxisKm: a, apogeeKm: apogee, perigeeKm: perigee, periodMin, regime, meanAltKm: (apogee + perigee) / 2 };
}

function classifyFreshnessLocal() {
  return "UNAVAILABLE"; // local fallback data is never presented as current
}

function normalizeLocal(raw) {
  const noradId = raw.NORAD_CAT_ID != null ? String(raw.NORAD_CAT_ID) : null;
  if (!noradId) return null;
  const meanMotion = raw.MEAN_MOTION != null ? parseFloat(raw.MEAN_MOTION) : null;
  const eccentricity = raw.ECCENTRICITY != null ? parseFloat(raw.ECCENTRICITY) : null;
  return {
    objectName: raw.OBJECT_NAME ? String(raw.OBJECT_NAME).trim() : "UNNAMED OBJECT",
    noradCatId: noradId,
    meanMotion, eccentricity,
    inclination: raw.INCLINATION != null ? parseFloat(raw.INCLINATION) : null,
    raan: raw.RA_OF_ASC_NODE != null ? parseFloat(raw.RA_OF_ASC_NODE) : null,
    argp: raw.ARG_OF_PERICENTER != null ? parseFloat(raw.ARG_OF_PERICENTER) : null,
    meanAnomaly: raw.MEAN_ANOMALY != null ? parseFloat(raw.MEAN_ANOMALY) : null,
    derived: meanMotion ? deriveOrbitLocal(meanMotion, eccentricity ?? 0) : null,
    freshness: classifyFreshnessLocal(),
    provenance: { provider: "local-fallback" },
  };
}

const FALLBACK_RAW = [
  { OBJECT_NAME: "ISS (ZARYA)", NORAD_CAT_ID: "25544", MEAN_MOTION: 15.5, ECCENTRICITY: 0.0004, INCLINATION: 51.64, RA_OF_ASC_NODE: 45.0, ARG_OF_PERICENTER: 90.0, MEAN_ANOMALY: 10.0 },
  { OBJECT_NAME: "TIANGONG", NORAD_CAT_ID: "48274", MEAN_MOTION: 15.6, ECCENTRICITY: 0.0006, INCLINATION: 41.47, RA_OF_ASC_NODE: 120.0, ARG_OF_PERICENTER: 60.0, MEAN_ANOMALY: 200.0 },
  { OBJECT_NAME: "NOAA 19", NORAD_CAT_ID: "33591", MEAN_MOTION: 14.1, ECCENTRICITY: 0.0013, INCLINATION: 99.05, RA_OF_ASC_NODE: 10.0, ARG_OF_PERICENTER: 300.0, MEAN_ANOMALY: 45.0 },
  { OBJECT_NAME: "GPS BIIR-2 (PRN 13)", NORAD_CAT_ID: "24876", MEAN_MOTION: 2.0, ECCENTRICITY: 0.01, INCLINATION: 55.0, RA_OF_ASC_NODE: 80.0, ARG_OF_PERICENTER: 200.0, MEAN_ANOMALY: 150.0 },
  { OBJECT_NAME: "GALILEO-FM2", NORAD_CAT_ID: "40129", MEAN_MOTION: 1.7, ECCENTRICITY: 0.002, INCLINATION: 56.0, RA_OF_ASC_NODE: 200.0, ARG_OF_PERICENTER: 100.0, MEAN_ANOMALY: 250.0 },
  { OBJECT_NAME: "GOES 16", NORAD_CAT_ID: "41866", MEAN_MOTION: 1.0027, ECCENTRICITY: 0.0001, INCLINATION: 0.05, RA_OF_ASC_NODE: 0.0, ARG_OF_PERICENTER: 0.0, MEAN_ANOMALY: 0.0 },
  { OBJECT_NAME: "METEOSAT-11", NORAD_CAT_ID: "40732", MEAN_MOTION: 1.0027, ECCENTRICITY: 0.0002, INCLINATION: 0.1, RA_OF_ASC_NODE: 40.0, ARG_OF_PERICENTER: 0.0, MEAN_ANOMALY: 90.0 },
  { OBJECT_NAME: "LANDSAT 9", NORAD_CAT_ID: "49260", MEAN_MOTION: 14.57, ECCENTRICITY: 0.0001, INCLINATION: 98.2, RA_OF_ASC_NODE: 300.0, ARG_OF_PERICENTER: 90.0, MEAN_ANOMALY: 30.0 },
  { OBJECT_NAME: "SENTINEL-2A", NORAD_CAT_ID: "40697", MEAN_MOTION: 14.3, ECCENTRICITY: 0.0001, INCLINATION: 98.6, RA_OF_ASC_NODE: 250.0, ARG_OF_PERICENTER: 80.0, MEAN_ANOMALY: 120.0 },
  { OBJECT_NAME: "MOLNIYA 1-80", NORAD_CAT_ID: "18820", MEAN_MOTION: 2.0, ECCENTRICITY: 0.72, INCLINATION: 63.4, RA_OF_ASC_NODE: 150.0, ARG_OF_PERICENTER: 270.0, MEAN_ANOMALY: 0.0 },
  { OBJECT_NAME: "CUBESAT XI-IV", NORAD_CAT_ID: "27848", MEAN_MOTION: 14.8, ECCENTRICITY: 0.0015, INCLINATION: 98.7, RA_OF_ASC_NODE: 20.0, ARG_OF_PERICENTER: 140.0, MEAN_ANOMALY: 300.0 },
  { OBJECT_NAME: "STARLINK-1130", NORAD_CAT_ID: "44714", MEAN_MOTION: 15.06, ECCENTRICITY: 0.0002, INCLINATION: 53.0, RA_OF_ASC_NODE: 190.0, ARG_OF_PERICENTER: 50.0, MEAN_ANOMALY: 60.0 },
];

const GROUPS = [
  { id: "STATIONS", label: "Space Stations" },
  { id: "GPS-OPS", label: "GPS Operational" },
  { id: "GNSS", label: "GNSS / Navigation" },
  { id: "WEATHER", label: "Weather" },
  { id: "EARTH-RESOURCES", label: "Earth Resources" },
  { id: "GEO", label: "Geostationary" },
  { id: "CUBESAT", label: "CubeSats" },
];

/* ============================================================
   Adapt backend's normalized SpaceObject JSON -> UI's canonical shape
   ============================================================ */
function fromBackendObject(o) {
  const apogee = o.derived?.apogee_altitude_km;
  const perigee = o.derived?.perigee_altitude_km;
  return {
    objectName: o.object_name || "UNNAMED OBJECT",
    noradCatId: o.norad_cat_id,
    meanMotion: o.elements?.mean_motion ?? null,
    eccentricity: o.elements?.eccentricity ?? null,
    inclination: o.elements?.inclination ?? null,
    raan: o.elements?.ra_of_asc_node ?? null,
    argp: o.elements?.arg_of_pericenter ?? null,
    meanAnomaly: o.elements?.mean_anomaly ?? null,
    derived: o.derived && o.derived.semi_major_axis_km != null ? {
      semiMajorAxisKm: o.derived.semi_major_axis_km,
      apogeeKm: apogee, perigeeKm: perigee,
      periodMin: o.derived.period_minutes,
      regime: o.derived.orbit_regime,
      meanAltKm: apogee != null && perigee != null ? (apogee + perigee) / 2 : null,
    } : null,
    freshness: o.orbital_provenance?.data_status || "UNAVAILABLE",
    provenance: {
      provider: o.orbital_provenance?.provider,
      retrievedAt: o.orbital_provenance?.retrieved_at ? new Date(o.orbital_provenance.retrieved_at) : null,
    },
  };
}

/* ============================================================
   DATA HOOK -- backend API first, local labeled fallback only if
   the backend itself is unreachable (not started, wrong URL, etc.)
   ============================================================ */
function useSpaceCatalog(group) {
  const [state, setState] = useState({
    loading: true, objects: [], usingFallback: false, error: null,
    fetchedAt: null, dropped: 0,
  });

  const load = useCallback(async (grp, forceRefresh = false) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fetchObjects(grp, { forceRefresh });
      const objects = (data.objects || []).map(fromBackendObject);
      setState({
        loading: false, objects, usingFallback: false, error: null,
        fetchedAt: data.fetched_at ? new Date(data.fetched_at * 1000) : new Date(),
        dropped: data.dropped_on_ingest || 0,
      });
    } catch (err) {
      const objects = FALLBACK_RAW.map(normalizeLocal).filter(Boolean);
      setState({
        loading: false, objects, usingFallback: true,
        error: String(err.message || err), fetchedAt: new Date(), dropped: 0,
      });
    }
  }, []);

  useEffect(() => { load(group); }, [group, load]);

  return { ...state, reload: () => load(group, true) };
}

/* ============================================================
   3D ORBITAL VIEW (three.js, manual drag-rotate)
   ============================================================ */
function OrbitalGlobe({ objects }) {
  const mountRef = useRef(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const width = mount.clientWidth, height = mount.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 2.4, 9);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const rig = new THREE.Group();
    scene.add(rig);

    const EARTH_SCENE_R = 2.1;
    const earthWire = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_SCENE_R, 28, 20),
      new THREE.MeshBasicMaterial({ color: 0x1c2b42, wireframe: true, transparent: true, opacity: 0.55 })
    );
    rig.add(earthWire);
    const earthCore = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_SCENE_R * 0.985, 28, 20),
      new THREE.MeshBasicMaterial({ color: 0x0a1220, transparent: true, opacity: 0.85 })
    );
    rig.add(earthCore);

    const eqRing = new THREE.Mesh(
      new THREE.RingGeometry(EARTH_SCENE_R, EARTH_SCENE_R + 0.005, 64),
      new THREE.MeshBasicMaterial({ color: 0x4fd1c5, side: THREE.DoubleSide, transparent: true, opacity: 0.25 })
    );
    eqRing.rotation.x = Math.PI / 2;
    rig.add(eqRing);

    const satGroup = new THREE.Group();
    rig.add(satGroup);

    const scale = EARTH_SCENE_R / EARTH_RADIUS_KM;
    objects.forEach((o) => {
      if (!o.derived || o.meanAnomaly == null || o.raan == null || o.argp == null || o.inclination == null) return;
      const pos = orbitalElementsToPosition(
        o.derived.semiMajorAxisKm, o.eccentricity ?? 0, o.inclination, o.raan, o.argp, o.meanAnomaly
      );
      const color = COLORS.regime[o.derived.regime] || COLORS.regime.UNKNOWN;
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.035, 8, 8),
        new THREE.MeshBasicMaterial({ color })
      );
      mesh.position.set(pos.x * scale, pos.z * scale, pos.y * scale);
      satGroup.add(mesh);
    });

    let dragging = false, lastX = 0, lastY = 0, autoRotate = true;
    let rotX = 0.25, rotY = 0.4;

    const onDown = (e) => { dragging = true; autoRotate = false; lastX = e.clientX ?? e.touches?.[0]?.clientX; lastY = e.clientY ?? e.touches?.[0]?.clientY; };
    const onUp = () => { dragging = false; };
    const onMove = (e) => {
      if (!dragging) return;
      const x = e.clientX ?? e.touches?.[0]?.clientX;
      const y = e.clientY ?? e.touches?.[0]?.clientY;
      rotY += (x - lastX) * 0.006;
      rotX += (y - lastY) * 0.006;
      rotX = Math.max(-1.2, Math.min(1.2, rotX));
      lastX = x; lastY = y;
    };
    renderer.domElement.addEventListener("mousedown", onDown);
    renderer.domElement.addEventListener("touchstart", onDown, { passive: true });
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchend", onUp);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onMove, { passive: true });

    let raf;
    const animate = () => {
      if (autoRotate) rotY += 0.0015;
      rig.rotation.y = rotY;
      rig.rotation.x = rotX;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };
    animate();

    const onResize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      camera.aspect = w / h; camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchend", onUp);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onMove);
      renderer.domElement.removeEventListener("mousedown", onDown);
      renderer.domElement.removeEventListener("touchstart", onDown);
      renderer.dispose();
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
  }, [objects]);

  return <div ref={mountRef} style={{ width: "100%", height: "100%", cursor: "grab" }} />;
}

/* ============================================================
   SMALL UI PIECES
   ============================================================ */
function KpiCard({ label, value, unit, accent }) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.hairline}`, borderRadius: 10, padding: "14px 16px", minWidth: 128, flex: "1 1 128px" }}>
      <div style={{ fontFamily: FONT_MONO, fontSize: 10, letterSpacing: 1.2, color: COLORS.textMuted, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 600, color: accent || COLORS.textPrimary, marginTop: 4 }}>
        {value}{unit && <span style={{ fontSize: 13, color: COLORS.textMuted, fontFamily: FONT_MONO, marginLeft: 4 }}>{unit}</span>}
      </div>
    </div>
  );
}

function FreshnessBadge({ status }) {
  const c = COLORS.freshness[status] || COLORS.freshness.UNAVAILABLE;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontFamily: FONT_MONO, fontSize: 10.5, letterSpacing: 0.6, color: c, border: `1px solid ${c}55`, background: `${c}14`, padding: "2px 7px", borderRadius: 20, textTransform: "uppercase" }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: c, display: "inline-block" }} />
      {status}
    </span>
  );
}

function RegimeDot({ regime }) {
  const c = COLORS.regime[regime] || COLORS.regime.UNKNOWN;
  return <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: c, marginRight: 6 }} />;
}

function histogram(values, bucketSize, labelFn) {
  if (!values.length) return [];
  const min = Math.floor(Math.min(...values) / bucketSize) * bucketSize;
  const max = Math.ceil(Math.max(...values) / bucketSize) * bucketSize;
  const buckets = {};
  for (let b = min; b < max; b += bucketSize) buckets[b] = 0;
  values.forEach((v) => {
    const b = Math.floor(v / bucketSize) * bucketSize;
    buckets[b] = (buckets[b] || 0) + 1;
  });
  return Object.entries(buckets).map(([b, count]) => ({ bucket: labelFn(Number(b)), count, raw: Number(b) })).sort((a, b) => a.raw - b.raw);
}

/* ============================================================
   MAIN DASHBOARD
   ============================================================ */
export default function App() {
  const [group, setGroup] = useState("STATIONS");
  const [groupMenuOpen, setGroupMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [regimeFilter, setRegimeFilter] = useState("ALL");
  const { loading, objects, usingFallback, error, fetchedAt, dropped, reload } = useSpaceCatalog(group);

  const filtered = useMemo(() => {
    return objects.filter((o) => {
      if (regimeFilter !== "ALL" && (o.derived?.regime || "UNKNOWN") !== regimeFilter) return false;
      if (search && !o.objectName.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [objects, search, regimeFilter]);

  const stats = useMemo(() => {
    const withOrbit = objects.filter((o) => o.derived);
    const regimeCounts = { LEO: 0, MEO: 0, GEO: 0, HEO: 0, UNKNOWN: 0 };
    withOrbit.forEach((o) => { regimeCounts[o.derived.regime] = (regimeCounts[o.derived.regime] || 0) + 1; });
    const freshnessCounts = { CURRENT: 0, RECENT: 0, STALE: 0, UNAVAILABLE: 0 };
    objects.forEach((o) => { freshnessCounts[o.freshness] = (freshnessCounts[o.freshness] || 0) + 1; });
    const inclinations = objects.map((o) => o.inclination).filter((v) => v != null);
    const altitudes = withOrbit.map((o) => o.derived.meanAltKm).filter((v) => v != null);
    return {
      total: objects.length, regimeCounts, freshnessCounts,
      avgInclination: inclinations.length ? inclinations.reduce((a, b) => a + b, 0) / inclinations.length : null,
      avgAltitude: altitudes.length ? altitudes.reduce((a, b) => a + b, 0) / altitudes.length : null,
    };
  }, [objects]);

  const regimeChartData = ["LEO", "MEO", "GEO", "HEO", "UNKNOWN"].map((r) => ({ regime: r, count: stats.regimeCounts[r] || 0 })).filter((d) => d.count > 0);
  const inclinationChart = histogram(objects.map((o) => o.inclination).filter((v) => v != null), 10, (b) => `${b}°`);
  const altitudeChart = histogram(objects.filter((o) => o.derived?.meanAltKm != null).map((o) => o.derived.meanAltKm), 2000, (b) => `${(b / 1000).toFixed(0)}k`);

  return (
    <div style={{ background: COLORS.bg, color: COLORS.textPrimary, minHeight: "100vh", fontFamily: FONT_DISPLAY, padding: "0 0 40px 0" }}>
      <style>{`
        * { box-sizing: border-box; }
        ::selection { background: ${COLORS.teal}33; }
        .sad-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .sad-scroll::-webkit-scrollbar-thumb { background: ${COLORS.hairline}; border-radius: 4px; }
        button:focus-visible, input:focus-visible { outline: 2px solid ${COLORS.teal}; outline-offset: 2px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (max-width: 760px) {
          .sad-grid { grid-template-columns: 1fr !important; }
          .sad-globe { height: 280px !important; }
        }
      `}</style>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, padding: "20px 24px", borderBottom: `1px solid ${COLORS.hairline}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Satellite size={20} color={COLORS.teal} />
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: 0.2 }}>Global Space Assets</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textMuted, letterSpacing: 0.5 }}>ORBITAL CATALOG — CELESTRAK GP DATA VIA BACKEND</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <button onClick={() => setGroupMenuOpen((v) => !v)} style={{ display: "flex", alignItems: "center", gap: 6, background: COLORS.surface, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, padding: "8px 12px", color: COLORS.textPrimary, fontFamily: FONT_MONO, fontSize: 12, cursor: "pointer" }}>
              {GROUPS.find((g) => g.id === group)?.label || group}
              <ChevronDown size={14} color={COLORS.textMuted} />
            </button>
            {groupMenuOpen && (
              <div style={{ position: "absolute", right: 0, top: "110%", background: COLORS.surfaceRaised, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, overflow: "hidden", zIndex: 20, minWidth: 190 }}>
                {GROUPS.map((g) => (
                  <div key={g.id} onClick={() => { setGroup(g.id); setGroupMenuOpen(false); }}
                    style={{ padding: "9px 12px", fontSize: 12.5, fontFamily: FONT_MONO, cursor: "pointer", color: g.id === group ? COLORS.teal : COLORS.textPrimary, background: g.id === group ? `${COLORS.teal}14` : "transparent" }}>
                    {g.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={reload} title="Re-fetch (force refresh)" style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: `1px solid ${COLORS.hairline}`, borderRadius: 8, padding: "8px 10px", color: COLORS.textMuted, cursor: "pointer" }}>
            <RefreshCw size={14} style={{ animation: loading ? "spin 1s linear infinite" : "none" }} />
          </button>
        </div>
      </div>

      {usingFallback && (
        <div style={{ margin: "14px 24px 0", padding: "10px 14px", borderRadius: 8, background: `${COLORS.amber}12`, border: `1px solid ${COLORS.amber}44`, display: "flex", gap: 10, alignItems: "flex-start", fontSize: 12.5, color: COLORS.textPrimary }}>
          <AlertTriangle size={16} color={COLORS.amber} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <strong style={{ color: COLORS.amber }}>Backend unreachable</strong> at <span style={{ fontFamily: FONT_MONO }}>{API_BASE}</span>
            {" "}(<span style={{ fontFamily: FONT_MONO }}>{error}</span>). Start it with <code style={{ fontFamily: FONT_MONO }}>uvicorn main:app --reload</code> in{" "}
            <code style={{ fontFamily: FONT_MONO }}>backend/</code>. Showing a small, clearly-labeled local demo dataset instead —
            every record below is tagged <FreshnessBadge status="UNAVAILABLE" /> for that reason.
          </div>
        </div>
      )}

      <div className="sad-grid" style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 16, padding: "20px 24px 0" }}>
        <div className="sad-globe" style={{ background: `radial-gradient(circle at 30% 30%, ${COLORS.surfaceRaised}, ${COLORS.bg})`, border: `1px solid ${COLORS.hairline}`, borderRadius: 14, height: 380, position: "relative", overflow: "hidden" }}>
          <OrbitalGlobe objects={objects} />
          <div style={{ position: "absolute", left: 14, top: 12, fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textMuted, letterSpacing: 0.5 }}>
            DRAG TO ROTATE · POSITIONS FROM TWO-BODY APPROXIMATION, NOT SGP4
          </div>
          <div style={{ position: "absolute", right: 14, bottom: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            {["LEO", "MEO", "GEO", "HEO"].map((r) => (
              <div key={r} style={{ display: "flex", alignItems: "center", fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textMuted }}>
                <RegimeDot regime={r} />{r}
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <KpiCard label="Total Objects" value={loading ? "—" : stats.total} accent={COLORS.teal} />
            <KpiCard label="Avg Altitude" value={loading || !stats.avgAltitude ? "—" : Math.round(stats.avgAltitude).toLocaleString()} unit="km" />
            <KpiCard label="Avg Inclination" value={loading || !stats.avgInclination ? "—" : stats.avgInclination.toFixed(1)} unit="°" />
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {["LEO", "MEO", "GEO", "HEO"].map((r) => (
              <KpiCard key={r} label={r} value={loading ? "—" : (stats.regimeCounts[r] || 0)} accent={COLORS.regime[r]} />
            ))}
          </div>
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.hairline}`, borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: FONT_MONO, fontSize: 10, color: COLORS.textMuted, letterSpacing: 1, textTransform: "uppercase" }}>
              <Info size={12} /> Source &amp; freshness
            </div>
            <div style={{ fontSize: 12.5, display: "flex", justifyContent: "space-between" }}><span>Provider</span><span style={{ fontFamily: FONT_MONO, color: COLORS.textMuted }}>{usingFallback ? "local-fallback" : "backend → CelesTrak"}</span></div>
            <div style={{ fontSize: 12.5, display: "flex", justifyContent: "space-between" }}><span>Retrieved</span><span style={{ fontFamily: FONT_MONO, color: COLORS.textMuted }}>{fetchedAt ? fetchedAt.toLocaleString() : "—"}</span></div>
            <div style={{ fontSize: 12.5, display: "flex", justifyContent: "space-between" }}><span>Dropped on ingest</span><span style={{ fontFamily: FONT_MONO, color: COLORS.textMuted }}>{dropped}</span></div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 }}>
              {Object.entries(stats.freshnessCounts).filter(([, c]) => c > 0).map(([status, count]) => (
                <div key={status} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <FreshnessBadge status={status} /><span style={{ fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textFaint }}>×{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="sad-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, padding: "16px 24px 0" }}>
        <ChartPanel title="Orbit Regime">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={regimeChartData}>
              <CartesianGrid stroke={COLORS.hairline} vertical={false} />
              <XAxis dataKey="regime" tick={{ fill: COLORS.textMuted, fontSize: 11, fontFamily: FONT_MONO }} axisLine={{ stroke: COLORS.hairline }} tickLine={false} />
              <YAxis tick={{ fill: COLORS.textMuted, fontSize: 10, fontFamily: FONT_MONO }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: COLORS.surfaceRaised, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, fontFamily: FONT_MONO, fontSize: 12 }} cursor={{ fill: COLORS.hairline + "44" }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>{regimeChartData.map((d, idx) => <Cell key={idx} fill={COLORS.regime[d.regime]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Inclination Distribution">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={inclinationChart}>
              <CartesianGrid stroke={COLORS.hairline} vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: COLORS.textMuted, fontSize: 10, fontFamily: FONT_MONO }} axisLine={{ stroke: COLORS.hairline }} tickLine={false} interval={Math.ceil(inclinationChart.length / 6)} />
              <YAxis tick={{ fill: COLORS.textMuted, fontSize: 10, fontFamily: FONT_MONO }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: COLORS.surfaceRaised, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, fontFamily: FONT_MONO, fontSize: 12 }} cursor={{ fill: COLORS.hairline + "44" }} />
              <Bar dataKey="count" fill={COLORS.violet} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Altitude Distribution">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={altitudeChart}>
              <CartesianGrid stroke={COLORS.hairline} vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: COLORS.textMuted, fontSize: 10, fontFamily: FONT_MONO }} axisLine={{ stroke: COLORS.hairline }} tickLine={false} interval={Math.ceil(altitudeChart.length / 6)} />
              <YAxis tick={{ fill: COLORS.textMuted, fontSize: 10, fontFamily: FONT_MONO }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background: COLORS.surfaceRaised, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, fontFamily: FONT_MONO, fontSize: 12 }} cursor={{ fill: COLORS.hairline + "44" }} />
              <Bar dataKey="count" fill={COLORS.teal} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>

      <div style={{ padding: "20px 24px 0" }}>
        <div style={{ display: "flex", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, background: COLORS.surface, border: `1px solid ${COLORS.hairline}`, borderRadius: 8, padding: "8px 12px", flex: "1 1 220px" }}>
            <Search size={14} color={COLORS.textMuted} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by object name…" style={{ background: "transparent", border: "none", outline: "none", color: COLORS.textPrimary, fontFamily: FONT_MONO, fontSize: 12.5, width: "100%" }} />
            {search && <X size={13} color={COLORS.textMuted} style={{ cursor: "pointer" }} onClick={() => setSearch("")} />}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {["ALL", "LEO", "MEO", "GEO", "HEO"].map((r) => (
              <button key={r} onClick={() => setRegimeFilter(r)} style={{ fontFamily: FONT_MONO, fontSize: 11, padding: "8px 12px", borderRadius: 8, cursor: "pointer", border: `1px solid ${regimeFilter === r ? COLORS.teal : COLORS.hairline}`, background: regimeFilter === r ? `${COLORS.teal}14` : "transparent", color: regimeFilter === r ? COLORS.teal : COLORS.textMuted }}>{r}</button>
            ))}
          </div>
        </div>

        <div className="sad-scroll" style={{ border: `1px solid ${COLORS.hairline}`, borderRadius: 10, overflow: "auto", maxHeight: 420 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ position: "sticky", top: 0, background: COLORS.surfaceRaised, zIndex: 1 }}>
                {["Object", "NORAD ID", "Regime", "Altitude (km)", "Inclination", "Period (min)", "Freshness"].map((h) => (
                  <th key={h} style={{ textAlign: "left", padding: "9px 12px", fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textMuted, letterSpacing: 0.6, textTransform: "uppercase", borderBottom: `1px solid ${COLORS.hairline}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={7} style={{ padding: 24, textAlign: "center", color: COLORS.textFaint, fontFamily: FONT_MONO, fontSize: 12 }}>{loading ? "Loading catalog…" : "No objects match this filter."}</td></tr>
              )}
              {filtered.map((o) => (
                <tr key={o.noradCatId} style={{ borderBottom: `1px solid ${COLORS.hairline}` }}>
                  <td style={{ padding: "9px 12px" }}>{o.objectName}</td>
                  <td style={{ padding: "9px 12px", fontFamily: FONT_MONO, color: COLORS.textMuted }}>{o.noradCatId}</td>
                  <td style={{ padding: "9px 12px" }}><RegimeDot regime={o.derived?.regime || "UNKNOWN"} /><span style={{ fontFamily: FONT_MONO, fontSize: 11.5 }}>{o.derived?.regime || "UNKNOWN"}</span></td>
                  <td style={{ padding: "9px 12px", fontFamily: FONT_MONO, color: COLORS.textMuted }}>{o.derived?.meanAltKm != null ? Math.round(o.derived.meanAltKm).toLocaleString() : "—"}</td>
                  <td style={{ padding: "9px 12px", fontFamily: FONT_MONO, color: COLORS.textMuted }}>{o.inclination != null ? `${o.inclination.toFixed(1)}°` : "—"}</td>
                  <td style={{ padding: "9px 12px", fontFamily: FONT_MONO, color: COLORS.textMuted }}>{o.derived?.periodMin != null ? o.derived.periodMin.toFixed(1) : "—"}</td>
                  <td style={{ padding: "9px 12px" }}><FreshnessBadge status={o.freshness} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textFaint, marginTop: 8 }}>Showing {filtered.length} of {objects.length} objects in group {group}.</div>
      </div>
    </div>
  );
}

function ChartPanel({ title, children }) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.hairline}`, borderRadius: 10, padding: "12px 14px" }}>
      <div style={{ fontFamily: FONT_MONO, fontSize: 10.5, color: COLORS.textMuted, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  );
}
