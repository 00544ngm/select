"use client";

import { directionFinalScore, rankDirections, splitDirectionName } from "@/lib/result-workbench";
import type { StructuredDirection } from "@/lib/api/types";
import { buildDecisionGuidance } from "@/lib/decision-guidance";
import { relationLabel } from "@/lib/result-labels";

export default function DirectionList({ directions, activeName, onSelect }: {
  directions: StructuredDirection[];
  activeName: string;
  onSelect: (direction: StructuredDirection) => void;
}) {
  const ranked = rankDirections(directions);

  return (
    <nav aria-label="辅品方向" className="min-w-0 overflow-x-auto border-b bg-muted/20 lg:max-h-[720px] lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <div className="flex min-w-max lg:block lg:min-w-0">
        {ranked.map((direction, index) => {
          const active = activeName === direction.name;
          const title = splitDirectionName(direction.name).zh;
          const score = directionFinalScore(direction);
          const status = buildDecisionGuidance(direction).title;
          return (
            <button
              key={direction.name}
              type="button"
              aria-current={active ? "true" : undefined}
              aria-label={`${title}，粘性潜力 ${score}，${status}`}
              onClick={() => onSelect(direction)}
              className={`grid w-72 shrink-0 grid-cols-[32px_minmax(0,1fr)_42px] items-center gap-2 border-b px-3 py-3 text-left transition-colors lg:w-full ${
                active ? "border-l-2 border-l-primary bg-background" : "border-l-2 border-l-transparent hover:bg-background/70"
              }`}
            >
              <span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{title}</span>
                <span className="mt-1 block truncate text-xs text-muted-foreground">
                  {[relationLabel(direction.primary_relation || direction.type), status].filter(Boolean).join(" · ")}
                </span>
              </span>
              <strong className="text-right text-base text-primary tabular-nums">
                {score || "-"}
              </strong>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
