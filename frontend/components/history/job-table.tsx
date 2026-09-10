"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, CheckSquare, ChevronLeft, ChevronRight, ExternalLink, FileDown, FileSpreadsheet, RotateCcw } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import JobNameEditor from "@/components/history/job-name-editor";
import ProductMedia from "@/components/jobs/product-media";
import { downloadArtifact, renameJob, retryJob } from "@/lib/api/jobs";
import { ApiError } from "@/lib/api/client";
import { beijingDateKey, formatBeijingTime, formatDuration } from "@/lib/job-time";
import { directionQuery, splitDirectionName } from "@/lib/result-workbench";
import { queryKeys } from "@/lib/query-keys";
import { cleanLabel } from "@/lib/result-format";
import type { JobListResponse, JobSummary } from "@/lib/api/types";

const modeLabels: Record<string, string> = { hypothesis: "假设分析", judgment: "对比审判", batch: "批量处理" };
const statusLabels: Record<string, string> = { queued: "排队中", running: "处理中", completed: "已完成", failed: "失败", interrupted: "已中断" };
const rowGrid = "grid min-w-0 gap-3 px-3 py-3 sm:grid-cols-2 lg:grid-cols-[36px_150px_minmax(220px,1.25fr)_minmax(220px,1fr)_140px_100px_48px] lg:items-center";

interface JobTableProps { jobs: JobSummary[]; total: number; page: number; pageSize: number; onPageChange: (page: number) => void; }

function dateLabel(key: string, now = new Date()): string {
  if (!key) return "日期不可用";
  const today = beijingDateKey(now);
  const yesterday = beijingDateKey(new Date(now.getTime() - 86_400_000));
  const [year, month, day] = key.split("-").map(Number);
  const full = `${year}年${month}月${day}日`;
  return key === today ? `今天 · ${full}` : key === yesterday ? `昨天 · ${full}` : full;
}

function MatchTime({ job, now }: { job: JobSummary; now: Date }) {
  const terminal = job.status === "completed" || job.status === "failed";
  return <div className="min-w-0 text-xs">
    <p className="font-medium tabular-nums">{formatBeijingTime(job.created_at)} 开始</p>
    {terminal ? <><p className="mt-1 tabular-nums text-muted-foreground">{formatBeijingTime(job.updated_at)} {job.status === "completed" ? "完成" : "结束"}</p><p className="mt-1 text-muted-foreground">{formatDuration(job.created_at, job.updated_at)}</p></> : job.status === "running" ? <p className="mt-1 text-muted-foreground">已运行 {formatDuration(job.created_at, now)}</p> : null}
  </div>;
}

interface JobAndProductProps {
  job: JobSummary;
  editing: boolean;
  saving: boolean;
  error?: string;
  onStartEditing: () => void;
  onSave: (name: string | null) => void;
  onCancel: () => void;
}

function JobAndProduct({ job, editing, saving, error, onStartEditing, onSave, onCancel }: JobAndProductProps) {
  return <div className="flex min-w-0 items-center gap-3">
    <a href={`/jobs/${job.id}`} aria-label={`查看任务 ${job.id}`} className="shrink-0 hover:opacity-80">
      <ProductMedia src={job.product_image ?? undefined} alt={job.product_title || job.name || `任务 ${job.id}`} emptyLabel="历史无图" className="w-11" />
    </a>
    <span className="min-w-0 flex-1">
      <JobNameEditor name={job.name ?? null} editing={editing} saving={saving} error={error} onStart={onStartEditing} onSave={onSave} onCancel={onCancel} />
      <a href={`/jobs/${job.id}`} className="block min-w-0 hover:underline">
        <span className="mt-0.5 block text-[11px] text-muted-foreground">{modeLabels[job.mode] ?? job.mode}</span>
        <span className="mt-0.5 block break-words text-xs text-muted-foreground">{job.product_title || "未保存主品标题"}</span>
        <span className="mt-1 block truncate font-mono text-[11px] text-muted-foreground">{job.id}</span>
      </a>
    </span>
  </div>;
}

function renameErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return "任务不存在或已被删除";
  if (error instanceof ApiError && error.status === 422) return "任务备注不能超过 100 个字符";
  return "保存失败，请稍后重试";
}

function DirectionSummary({ job }: { job: JobSummary }) {
  if (!job.top_direction_name) return <p className="text-sm text-muted-foreground">未生成匹配结果</p>;
  const name = splitDirectionName(job.top_direction_name);
  const query = directionQuery({ name: job.top_direction_name, keywords: job.top_direction_keywords });
  return <div className="min-w-0"><p className="break-words text-sm font-medium">{name.zh || job.top_direction_name}</p>{name.en && <p className="mt-0.5 break-words text-xs text-muted-foreground">{name.en}</p>}{query && <p className="keyword-text mt-1 break-all text-xs text-primary">{query}</p>}</div>;
}

function ResultSummary({ job }: { job: JobSummary }) {
  const grade = cleanLabel(job.grade);
  const hasDirectionScore = typeof job.top_direction_score === "number";
  const hasOverallScore = typeof job.score === "number";
  return <div className="min-w-0 text-xs">
    {job.provider && job.provider_model && <p className="mb-1 break-all text-muted-foreground">{job.provider} · {job.provider_model}</p>}
    {hasDirectionScore ? <p className="font-semibold tabular-nums text-primary">方向分 {job.top_direction_score}</p> : <p className="text-muted-foreground">没有评分</p>}
    {hasOverallScore && <p className="mt-1 tabular-nums">综合 {job.score}</p>}
    {job.top_direction_type && <p className="mt-1 break-words text-muted-foreground">{job.top_direction_type}</p>}
    {grade && <p className="mt-1 text-muted-foreground">评级 {grade}</p>}
    {(job.status === "failed" || job.status === "interrupted") && job.error_message && <p className="mt-1 break-words text-destructive">{job.error_message}</p>}
  </div>;
}

export default function JobTable({ jobs, total, page, pageSize, onPageChange }: JobTableProps) {
  const queryClient = useQueryClient();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [scoreSort, setScoreSort] = useState<"none" | "desc" | "asc">("none");
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!jobs.some((job) => job.status === "running")) return;
    const interval = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(interval);
  }, [jobs]);
  const retryMutation = useMutation({ mutationFn: (jobId: string) => retryJob(jobId), onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all }) });
  const renameMutation = useMutation({
    mutationFn: ({ jobId, name }: { jobId: string; name: string | null }) => renameJob(jobId, name),
    onMutate: () => setRenameError(null),
    onSuccess: (updated) => {
      queryClient.setQueriesData<JobListResponse>({ queryKey: queryKeys.jobs.all }, (current) => current ? { ...current, items: current.items.map((item) => item.id === String(updated.id) ? { ...item, name: updated.name } : item) } : current);
      setEditingJobId(null);
      setRenameError(null);
    },
    onError: (error) => setRenameError(renameErrorMessage(error)),
  });
  const sortedJobs = useMemo(() => scoreSort === "none" ? jobs : [...jobs].sort((a, b) => (scoreSort === "desc" ? -1 : 1) * ((a.score ?? -1) - (b.score ?? -1))), [jobs, scoreSort]);
  const groups = useMemo(() => {
    const grouped = new Map<string, JobSummary[]>();
    sortedJobs.forEach((job) => { const key = beijingDateKey(job.created_at); grouped.set(key, [...(grouped.get(key) ?? []), job]); });
    return [...grouped.entries()];
  }, [sortedJobs]);
  const completedJobs = jobs.filter((job) => job.status === "completed");
  const allCompletedSelected = completedJobs.length > 0 && completedJobs.every((job) => selectedIds.has(job.id));
  const toggleSelect = (id: string) => setSelectedIds((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; });
  const toggleSelectAll = () => setSelectedIds((current) => { const next = new Set(current); completedJobs.forEach((job) => allCompletedSelected ? next.delete(job.id) : next.add(job.id)); return next; });
  const handleDownload = async (kind: "json" | "excel") => {
    for (const jobId of selectedIds) {
      try { const blob = await downloadArtifact(jobId, kind); const objectUrl = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = objectUrl; anchor.download = `${jobId}.${kind === "json" ? "json" : "xlsx"}`; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(objectUrl); await new Promise((resolve) => setTimeout(resolve, 300)); } catch { /* skip failed downloads */ }
    }
  };
  const cycleScoreSort = () => setScoreSort((state) => state === "none" ? "desc" : state === "desc" ? "asc" : "none");

  if (!jobs.length) return <p className="py-8 text-center text-sm text-muted-foreground">暂无任务记录</p>;
  return <div className="space-y-4">
    {selectedIds.size > 0 && <div className="flex flex-wrap items-center gap-3 border bg-muted/30 px-4 py-2.5"><span className="text-sm text-muted-foreground">已选 {selectedIds.size} 项</span><button type="button" onClick={() => handleDownload("json")} className="inline-flex items-center gap-1.5 border bg-background px-3 py-1.5 text-sm"><FileDown className="h-3.5 w-3.5" />批量下载 JSON</button><button type="button" onClick={() => handleDownload("excel")} className="inline-flex items-center gap-1.5 border bg-background px-3 py-1.5 text-sm"><FileSpreadsheet className="h-3.5 w-3.5" />批量下载 Excel</button><button type="button" onClick={() => setSelectedIds(new Set())} className="ml-auto text-sm text-muted-foreground">取消选择</button></div>}
    <div className="overflow-hidden border">
      <div className={`${rowGrid} hidden border-b bg-muted/50 text-xs font-medium text-muted-foreground lg:grid`}><button type="button" onClick={toggleSelectAll} aria-label={allCompletedSelected ? "取消全选" : "全选"} className="justify-self-center"><CheckSquare className="h-4 w-4" /></button><span>匹配时间</span><span>任务与主品</span><span>最高分辅品方向</span><button type="button" onClick={cycleScoreSort} className="inline-flex items-center gap-1"><ArrowUpDown className="h-3 w-3" />结果{scoreSort === "desc" ? " ↓" : scoreSort === "asc" ? " ↑" : ""}</button><span>状态</span><span className="text-right">操作</span></div>
      {groups.map(([key, group]) => <section key={key} aria-labelledby={`history-${key || "unknown"}`}><h2 id={`history-${key || "unknown"}`} className="border-b bg-muted/20 px-3 py-2 text-xs font-semibold text-muted-foreground">{dateLabel(key)}</h2>{group.map((job) => {
        const isCompleted = job.status === "completed"; const checked = selectedIds.has(job.id);
        return <article key={job.id} className={`${rowGrid} border-b last:border-b-0 ${checked ? "bg-muted/20" : ""}`}>
          <div className="flex items-center lg:justify-center">{isCompleted && <input type="checkbox" checked={checked} onChange={() => toggleSelect(job.id)} className="h-4 w-4 accent-foreground" aria-label={`选择任务 ${job.id}`} />}</div>
          <div className="min-w-0"><span className="mb-1 block text-[11px] text-muted-foreground lg:hidden">匹配时间</span><MatchTime job={job} now={now} /></div>
          <div className="min-w-0 sm:col-span-2 lg:col-span-1"><span className="mb-1 block text-[11px] text-muted-foreground lg:hidden">任务与主品</span><JobAndProduct job={job} editing={editingJobId === job.id} saving={renameMutation.isPending && renameMutation.variables?.jobId === job.id} error={editingJobId === job.id ? renameError ?? undefined : undefined} onStartEditing={() => { setEditingJobId(job.id); setRenameError(null); }} onSave={(name) => renameMutation.mutate({ jobId: job.id, name })} onCancel={() => { setEditingJobId(null); setRenameError(null); }} /></div>
          <div className="min-w-0 sm:col-span-2 lg:col-span-1"><span className="mb-1 block text-[11px] text-muted-foreground lg:hidden">最高分辅品方向</span><DirectionSummary job={job} /></div>
          <div className="min-w-0"><span className="mb-1 block text-[11px] text-muted-foreground lg:hidden">结果</span><ResultSummary job={job} /></div>
          <div><span className="mb-1 block text-[11px] text-muted-foreground lg:hidden">状态</span><span className={`inline-block px-2 py-0.5 text-xs ${job.status === "completed" ? "bg-green-100 text-green-700" : job.status === "failed" ? "bg-red-100 text-red-700" : job.status === "interrupted" ? "bg-amber-100 text-amber-700" : job.status === "running" ? "bg-blue-100 text-blue-700" : "bg-muted text-muted-foreground"}`}>{job.status === "running" ? job.error_code === "WALMART_CAPTCHA_REQUIRED" ? "等待 Walmart 验证" : `处理中 ${job.progress}%` : statusLabels[job.status] ?? job.status}</span></div>
          <div className="flex justify-end gap-2"><a href={`/jobs/${job.id}`} aria-label="查看结果" className="grid h-8 w-8 place-items-center border text-muted-foreground"><ExternalLink className="h-3.5 w-3.5" /></a>{(job.status === "failed" || job.status === "interrupted") && <button type="button" onClick={() => retryMutation.mutate(job.id)} disabled={retryMutation.isPending} aria-label="重新提交" className="grid h-8 w-8 place-items-center border text-muted-foreground disabled:opacity-50"><RotateCcw className="h-3.5 w-3.5" /></button>}</div>
        </article>;
      })}</section>)}
    </div>
    {totalPages > 1 && <div className="flex items-center justify-between text-sm"><span className="text-muted-foreground">共 {total} 条 · 第 {page} / {totalPages} 页</span><div className="flex gap-1"><button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} className="grid h-8 w-8 place-items-center border disabled:opacity-40" aria-label="上一页"><ChevronLeft className="h-4 w-4" /></button><button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages} className="grid h-8 w-8 place-items-center border disabled:opacity-40" aria-label="下一页"><ChevronRight className="h-4 w-4" /></button></div></div>}
  </div>;
}
