"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { listJobs } from "@/lib/api/jobs";
import { queryKeys } from "@/lib/query-keys";
import HistoryFilters from "@/components/history/history-filters";
import JobTable from "@/components/history/job-table";
import type { JobMode, JobStatus } from "@/lib/api/types";

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const [modeFilter, setModeFilter] = useState<JobMode | "">("");
  const [statusFilter, setStatusFilter] = useState<JobStatus | "">("");

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: queryKeys.jobs.list({ page, mode: modeFilter, status: statusFilter }),
    queryFn: () =>
      listJobs({
        page,
        page_size: 20,
        mode: modeFilter || undefined,
        status: statusFilter || undefined,
      }),
  });

  return (
    <div className="mx-auto max-w-[1500px] space-y-4 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-lg font-semibold">任务历史</h1><p className="mt-1 text-sm text-muted-foreground">按匹配时间回看主品、最高分辅品方向和任务结果</p></div><p className="text-xs text-muted-foreground">时间显示：北京时间 UTC+8</p></div>
      <HistoryFilters
        mode={modeFilter}
        status={statusFilter}
        onModeChange={(m) => { setModeFilter(m); setPage(1); }}
        onStatusChange={(s) => { setStatusFilter(s); setPage(1); }}
      />
      {isLoading ? (
        <p className="py-8 text-center text-sm text-muted-foreground">加载中...</p>
      ) : isError ? (
        <div className="border border-destructive/30 bg-destructive/5 px-4 py-8 text-center">
          <p className="text-sm font-medium text-destructive">历史加载失败</p>
          <p className="mt-1 text-xs text-muted-foreground">历史数据暂时无法读取，请重试。</p>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            aria-label="重新加载历史"
            className="mx-auto mt-3 inline-flex items-center gap-1.5 border bg-background px-3 py-1.5 text-sm disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            重新加载历史
          </button>
        </div>
      ) : (
        <JobTable
          jobs={data?.items ?? []}
          total={data?.total ?? 0}
          page={page}
          pageSize={data?.page_size ?? 20}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}
