import type {
  IntakeAnswersRequest,
  ProjectCreateRequest,
  ProjectCreateResponse,
  ProjectDetailResponse,
  ProjectResponse,
  ProjectStateResponse,
  ResumeStageRunResponse,
  StageControlResponse,
  StageDecisionRequest,
  StageDecisionResponse,
  StageRunDetailResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getApiBaseUrl() {
  const envBase = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");

  if (typeof window !== "undefined") {
    return envBase || "/api/v1";
  }

  return envBase && envBase.startsWith("http") ? envBase : "http://localhost:8000/api/v1";
}

function formatApiMessage(status: number, detail: unknown) {
  if (status === 502 || status === 503 || status === 504) {
    return "后端服务暂时不可用，请稍后重试。";
  }
  if (typeof detail === "string") {
    if (detail.includes("<html") || detail.includes("Bad Gateway")) {
      return `请求失败，状态码 ${status}`;
    }
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String(item.msg);
        }
        return JSON.stringify(item);
      })
      .join("；");
  }
  return `请求失败，状态码 ${status}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : body;
    throw new ApiError(formatApiMessage(response.status, detail), response.status, detail);
  }

  return body as T;
}

function apiPath(path: string) {
  return `${getApiBaseUrl()}${path}`;
}

export const apiClient = {
  listProjects() {
    return requestJson<ProjectResponse[]>("/projects");
  },

  createProject(payload: ProjectCreateRequest) {
    return requestJson<ProjectCreateResponse>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getProject(projectId: string) {
    return requestJson<ProjectDetailResponse>(`/projects/${projectId}`);
  },

  getProjectState(projectId: string) {
    return requestJson<ProjectStateResponse>(`/projects/${projectId}/state`);
  },

  getStageRun(stageRunId: string, options?: { includeResult?: boolean }) {
    const includeResult = options?.includeResult ?? true;
    const query = includeResult ? "" : "?include_result=false";
    return requestJson<StageRunDetailResponse>(`/stage-runs/${stageRunId}${query}`);
  },

  submitIntakeAnswers(stageRunId: string, payload: IntakeAnswersRequest) {
    return requestJson<ResumeStageRunResponse>(`/stage-runs/${stageRunId}/intake-answers`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createStageDecision(projectId: string, stageKey: string, payload: StageDecisionRequest) {
    return requestJson<StageDecisionResponse>(`/projects/${projectId}/stages/${stageKey}/decisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  requestStageControl(
    projectId: string,
    stageKey: string,
    action: "skip" | "generate" | "redo",
    payload?: { source_version_id?: string; reason?: string },
  ) {
    return requestJson<StageControlResponse>(`/projects/${projectId}/stages/${stageKey}/${action}`, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
    });
  },

  getProposalMarkdownUrl(projectId: string) {
    return apiPath(`/projects/${projectId}/exports/proposal.md`);
  },

  getProposalZipUrl(projectId: string) {
    return apiPath(`/projects/${projectId}/exports/proposal.zip`);
  },

  getProjectAssetUrl(projectId: string, assetId: string) {
    return apiPath(`/projects/${projectId}/assets/${assetId}`);
  },
};
