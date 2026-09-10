export const queryKeys = {
  jobs: {
    all: ["jobs"] as const,
    list: (filters?: Record<string, unknown>) => ["jobs", "list", filters] as const,
    detail: (jobId: string) => ["jobs", "detail", jobId] as const,
  },
  providers: {
    all: ["providers"] as const,
  },
};
