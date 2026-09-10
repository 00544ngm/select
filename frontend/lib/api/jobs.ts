import { apiFetch, authHeaders, buildApiUrl, ApiError } from "./client";
import type {
  JobSummary,
  JobDetail,
  JobListResponse,
  HypothesisJobCreate,
  JudgmentJobCreate,
  BatchJobCreate,
  JobAttempt,
} from "./types";

export async function submitHypothesis(payload: HypothesisJobCreate): Promise<JobSummary> {
  return apiFetch<JobSummary>("/jobs/hypothesis", {
    method: "POST",
    body: payload,
  });
}

export async function submitJudgment(payload: JudgmentJobCreate): Promise<JobSummary> {
  return apiFetch<JobSummary>("/jobs/judgment", {
    method: "POST",
    body: payload,
  });
}

export async function submitBatch(payload: BatchJobCreate): Promise<JobSummary> {
  return apiFetch<JobSummary>("/jobs/batch", {
    method: "POST",
    body: payload,
  });
}

export async function listJobs(params?: {
  page?: number;
  page_size?: number;
  mode?: string;
  status?: string;
}): Promise<JobListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  if (params?.mode) searchParams.set("mode", params.mode);
  if (params?.status) searchParams.set("status", params.status);
  const qs = searchParams.toString();
  return apiFetch<JobListResponse>(`/jobs${qs ? `?${qs}` : ""}`);
}

export async function getJob(jobId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/jobs/${jobId}`);
}

export async function listJobAttempts(jobId: string): Promise<JobAttempt[]> {
  return apiFetch<JobAttempt[]>(`/jobs/${jobId}/attempts`);
}

export async function retryJob(jobId: string): Promise<JobSummary> {
  return apiFetch<JobSummary>(`/jobs/${jobId}/retry`, { method: "POST" });
}

export async function renameJob(jobId: string, name: string | null): Promise<JobSummary> {
  return apiFetch<JobSummary>(`/jobs/${jobId}/name`, {
    method: "PATCH",
    body: { name },
  });
}

export async function getJobResult(jobId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/jobs/${jobId}/result`);
}

export async function downloadArtifact(jobId: string, kind: string): Promise<Blob> {
  const url = await buildApiUrl(`/jobs/${jobId}/artifacts/${kind}`);
  const response = await fetch(url, { headers: await authHeaders() });
  if (!response.ok) {
    let code = "ARTIFACT_DOWNLOAD_FAILED";
    let message = `下载 ${kind} 产物失败（HTTP ${response.status}）`;
    let retryable = response.status >= 500;
    try {
      const json = await response.json();
      if (json?.detail?.code) {
        code = json.detail.code;
        message = json.detail.message;
        retryable = json.detail.retryable ?? retryable;
      }
    } catch {
      // non-JSON response, keep defaults
    }
    throw new ApiError(code, message, retryable, response.status);
  }
  return response.blob();
}
