"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import FieldGrid from "@/components/jobs/field-grid";
import { cleanLabel } from "@/lib/result-format";

interface Section {
  title: string;
  content?: string;
  children?: Section[];
}

interface ResultSectionsProps {
  sections?: Section[];
}

export default function ResultSections({ sections }: ResultSectionsProps) {
  const [openSet, setOpenSet] = useState<Set<number>>(new Set([0]));

  if (!sections || sections.length === 0) return null;

  const toggle = (i: number) => {
    setOpenSet((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-muted-foreground">详细对比</p>
      {sections.map((section, i) => (
        <div key={i} className="rounded-xl border">
          <button
            type="button"
            onClick={() => toggle(i)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium"
          >
            {cleanLabel(section.title)}
            {openSet.has(i) ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
          </button>
          {openSet.has(i) && section.children && (
            <div className="space-y-1.5 border-t px-4 py-3">
              {section.children.map((child, j) => (
                <NestedAccordion key={j} item={child} />
              ))}
            </div>
          )}
          {openSet.has(i) && section.content && !section.children && (
            <div className="border-t px-4 py-2">
              <FieldGrid content={section.content} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function NestedAccordion({ item }: { item: Section }) {
  const [open, setOpen] = useState(false);
  const hasChildren = item.children && item.children.length > 0;

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm"
      >
        <span className="font-medium">{cleanLabel(item.title)}</span>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="space-y-1.5 border-t px-3 py-2">
          {item.content && <FieldGrid content={item.content} dense />}
          {hasChildren &&
            item.children!.map((child, j) => (
              <NestedAccordion key={j} item={child} />
            ))}
        </div>
      )}
    </div>
  );
}
