export const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface Point3d {
  x: number;
  y: number;
  z: number;
}

export interface AdaptiveMoldParams {
  width: number;
  length: number;
  spacing: number;
  max_height: number;
  min_height: number;
  rod_base_length: number;
  panel_name: string;
}

export interface FabricabilityCheck {
  is_fabricable: boolean;
  violations: string[];
  warnings: string[];
  max_pin_step_mm: number;
  clamped_pin_count: number;
  out_of_bounds_pin_count: number;
}

export interface AdaptiveMoldResult {
  nx: number;
  ny: number;
  grid_pts: Point3d[];
  pin_heights: number[];
  pin_tops: Point3d[];
  clamp_flags: boolean[];
  extension_flags: boolean[];
  extension_method: string;
  optimization_info: string;
  info: string;
  fabricability?: FabricabilityCheck;
}

export interface SessionState {
  project_id: string;
  project_name: string;
  status: "idle" | "compute_requested" | "synced" | "error";
  params: AdaptiveMoldParams;
  result: AdaptiveMoldResult | null;
  gh_connected: boolean;
  last_sync_at: string | null;
  last_gh_ping_at: string | null;
  compute_requested_at: string | null;
  error_message: string | null;
}

export interface ProjectSummary {
  project_id: string;
  project_name: string;
  status: string;
  panel_name: string;
  actuator_count: number;
  last_sync_at: string | null;
}

export const api = {
  health: () =>
    request<{ status: string; gh_connected: boolean }>("/api/health"),

  getSession: () => request<SessionState>("/api/session"),

  updateParams: (params: AdaptiveMoldParams) =>
    request<SessionState>("/api/session/params", {
      method: "PUT",
      body: JSON.stringify({ params }),
    }),

  requestCompute: () =>
    request<SessionState>("/api/session/compute-request", { method: "POST" }),

  listProjects: () =>
    request<ProjectSummary[]>("/api/session/projects"),
};
