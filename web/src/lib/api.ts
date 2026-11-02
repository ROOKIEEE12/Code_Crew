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
export type Reference = S["Reference"];
export type ImageRef = S["ImageRef"];
export type DesignReview = S["DesignReview"];
export type DesignBrief = S["DesignBrief"];
export interface ImageUpload {
  media_type: string;
  /** base64, no data: prefix */
  data: string;
}

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
  verification_stale: boolean;
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
  verification_stale: boolean;
  history: { run_id: string; requirement: string; at: number; passed: boolean }[];
  files: Record<string, string>;
  tests: Record<string, string>;
  readme: string;
  created_at: number;
  updated_at: number;
}

export interface ExecResult {
  exit_code: number;
  output: string;
  timed_out: boolean;
  seconds: number;
  timeout_sec: number;
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
  health: () => request<{ status: string; version: string; providers_configured: string[]; stale?: boolean }>("/api/health"),
  providers: () => request<ProviderStatus>("/api/providers"),
  agents: () => request<{ agents: { id: string; name: string; role: string }[]; graph: string }>("/api/agents"),
  createRun: (requirement: string, ask = false, images: ImageUpload[] = []) =>
    request<RunState>("/api/runs", { method: "POST", body: JSON.stringify({ requirement, ask, images }) }),
  resumeRun: (runId: string) => request<RunState>(`/api/runs/${runId}/resume`, { method: "POST" }),
  answer: (runId: string, questionId: string, choice: number) =>
    request<{ accepted: boolean }>(`/api/runs/${runId}/answer`, { method: "POST", body: JSON.stringify({ question_id: questionId, choice }) }),
  sendMessage: (runId: string, text: string) =>
    request<{ id: string }>(`/api/runs/${runId}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  runs: (projectId?: string) =>
    request<{ runs: RunSummary[] }>(`/api/runs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  run: (id: string) => request<RunState>(`/api/runs/${id}`),
  deleteRun: (id: string) => request<void>(`/api/runs/${id}`, { method: "DELETE" }),
  cancelRun: (id: string) => request<{ cancelled: boolean }>(`/api/runs/${id}/cancel`, { method: "POST" }),
  projects: () => request<{ projects: ProjectSummary[] }>("/api/projects"),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  iterate: (id: string, req: string) =>
    request<RunState>(`/api/projects/${id}/runs`, { method: "POST", body: JSON.stringify({ request: req }) }),
  exec: (id: string, path: string, stdin: string) =>
    request<ExecResult>(`/api/projects/${id}/exec`, { method: "POST", body: JSON.stringify({ path, stdin }) }),
  renameProject: (id: string, name: string) =>
    request<{ name: string }>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  saveFile: (id: string, path: string, content: string) =>
    request<{ saved: boolean }>(`/api/projects/${id}/files/${path.split("/").map(encodeURIComponent).join("/")}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  evalResults: () => request<{ results: EvalResult[] }>("/api/eval"),
  evalResult: (name: string) => request<EvalResult>(`/api/eval/${name}`),
};

export const downloadUrl = (projectId: string) => `${API_URL}/api/projects/${projectId}/download`;
export const previewUrl = (projectId: string, path = "index.html") => `${API_URL}/api/projects/${projectId}/preview/${path}`;
export const eventsUrl = (runId: string) => `${API_URL}/api/runs/${runId}/events`;
export const imageUrl = (runId: string, imageId: number) => `${API_URL}/api/runs/${runId}/images/${imageId}`;
