import type { JobStatus } from "./api/types";

export function getJobPollingInterval(status: JobStatus): number | false {
  switch (status) {
    case "queued":
    case "running":
      return 1500;
    case "completed":
    case "failed":
    case "interrupted":
      return false;
  }
}
