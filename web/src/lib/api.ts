import type { components } from "./api-types";

type S = components["schemas"];
export type RunState = S["RunState"];
export type Spec = S["SpecOut"];
export type FileSpec = S["FileSpec"];
export type Verification = S["Verification"];
export type Issue = S["Issue"];
export type TestCase = S["TestCaseResult"];
export type DebugRound = S["DebugRound"];
export type Usage = S["Usage"];
export type Activity = S["ActivityEntry"];
export type Triage = S["TriageOut"];
export type RunStatus = RunState["status"];

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the CodeCrew API at ${API_URL}. Is the backend running (python server.py)?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export interface RunSummary {
  id: string;
  mode: "build" | "iterate";
  requirement: string;
  project_id: string | null;
  status: RunStatus;
  phase: string;
  created_at: number;
  finished_at: number | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  summary: string;
  passed: boolean | null;
  tests_total: number | null;
  tests_passed: number | null;
  legacy: boolean;
  file_count: number;
  created_at: number;
  updated_at: number;
}

export interface ProjectDetail {
  id: string;
  name: string;
  spec: Spec | null;
  verification: Verification | null;
  history: { run_id: string; requirement: string; at: number; passed: boolean }[];
  files: Record<string, string>;
  tests: Record<string, string>;
  readme: string;
  created_at: number;
  updated_at: number;
}

export interface ProviderStatus {
  order: string[];
  providers: Record<string, { configured: boolean; models: string[] }>;
  health: Record<string, { successes: number; failures: number; cooldown_remaining_sec: number; last_error: string }>;
}

export interface EvalSummaryMode {
  tasks: number;
  solved: number;
  solve_rate: number;
  hidden_test_pass_rate: number;
  avg_seconds: number;
  avg_llm_calls: number;
  avg_output_tokens: number;
  self_verified?: number;
  self_verified_and_solved?: number;
}

export interface EvalRow {
  task: string;
  mode: "baseline" | "codecrew";
  solved: boolean;
  hidden_passed: number;
  hidden_total: number;
  seconds: number;
  llm_calls: number;
  output_tokens: number;
  debug_rounds: number;
  self_verified: boolean | null;
  error: string | null;
}

export interface EvalResult {
  name: string;
  finished_at: number;
  providers: string[];
  summary: Record<string, EvalSummaryMode>;
  rows?: EvalRow[];
}

export const api = {
  health: () => request<{ status: string; version: string; providers_configured: string[] }>("/api/health"),
  providers: () => request<ProviderStatus>("/api/providers"),
  agents: () => request<{ agents: { id: string; name: string; role: string }[]; graph: string }>("/api/agents"),
  createRun: (requirement: string) => request<RunState>("/api/runs", { method: "POST", body: JSON.stringify({ requirement }) }),
  runs: (projectId?: string) =>
    request<{ runs: RunSummary[] }>(`/api/runs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  run: (id: string) => request<RunState>(`/api/runs/${id}`),
  cancelRun: (id: string) => request<{ cancelled: boolean }>(`/api/runs/${id}/cancel`, { method: "POST" }),
  projects: () => request<{ projects: ProjectSummary[] }>("/api/projects"),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  iterate: (id: string, req: string) =>
    request<RunState>(`/api/projects/${id}/runs`, { method: "POST", body: JSON.stringify({ request: req }) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  evalResults: () => request<{ results: EvalResult[] }>("/api/eval"),
  evalResult: (name: string) => request<EvalResult>(`/api/eval/${name}`),
};

export const downloadUrl = (projectId: string) => `${API_URL}/api/projects/${projectId}/download`;
export const previewUrl = (projectId: string, path = "index.html") => `${API_URL}/api/projects/${projectId}/preview/${path}`;
export const eventsUrl = (runId: string) => `${API_URL}/api/runs/${runId}/events`;
