import { apiFetch } from "./client";

export interface CrossReviewSelection { provider: string; model: string }

export function triggerCrossReview(jobId: string, reviewerA: CrossReviewSelection, reviewerB: CrossReviewSelection) {
  return apiFetch<{ status: string; job_id: string }>(`/jobs/${jobId}/cross-review`, {
    method: "POST",
    body: { reviewer_a: reviewerA, reviewer_b: reviewerB },
  });
}
