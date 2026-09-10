"use client";

export default function ServiceStatus() {
  return (
    <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
      <span className="flex h-2 w-2 rounded-full bg-green-500" />
      <span>服务正常</span>
    </div>
  );
}
