// The frontend's only network dependency is our own FastAPI backend.
// It never calls CelesTrak or Space-Track directly -- see ../backend.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function fetchGroups() {
  const res = await fetch(`${API_BASE}/api/groups`);
  if (!res.ok) throw new Error(`groups: HTTP ${res.status}`);
  return res.json();
}

export async function fetchObjects(group, { search, regime, forceRefresh } = {}) {
  const params = new URLSearchParams({ group });
  if (search) params.set("search", search);
  if (regime && regime !== "ALL") params.set("regime", regime);
  if (forceRefresh) params.set("force_refresh", "true");

  const res = await fetch(`${API_BASE}/api/objects?${params.toString()}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`objects: HTTP ${res.status} ${detail}`.trim());
  }
  return res.json();
}

export { API_BASE };
