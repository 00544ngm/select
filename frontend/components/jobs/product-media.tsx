"use client";

import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ProductMedia({ src, alt, emptyLabel = "暂无图片", className }: {
  src?: string | string[];
  alt: string;
  emptyLabel?: string;
  className?: string;
}) {
  const sources = Array.isArray(src) ? src.filter(Boolean) : src ? [src] : [];
  const sourceKey = sources.join("\u0000");
  const [sourceIndex, setSourceIndex] = useState(0);
  useEffect(() => setSourceIndex(0), [sourceKey]);
  const activeSrc = sources[sourceIndex];
  return (
    <div className={cn("grid aspect-square shrink-0 place-items-center overflow-hidden border bg-white", className)}>
      {activeSrc ? (
        <img src={activeSrc} alt={alt} onError={() => setSourceIndex((index) => index + 1)} className="h-full w-full object-contain p-2" />
      ) : (
        <div className="flex flex-col items-center gap-1 px-2 text-center text-xs text-muted-foreground">
          <ImageOff className="h-4 w-4" aria-hidden="true" />
          <span>{sources.length ? "图片加载失败" : emptyLabel}</span>
        </div>
      )}
    </div>
  );
}
