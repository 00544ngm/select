"use client";

import { parseFmtText, type ParsedField } from "@/lib/result-format";

/**
 * 字段网格：把「• 键: 值」文本渲染成 左标签 / 右内容 的结构化表格。
 * 替代原来的 whitespace-pre-wrap 流水账展示。
 * 传 content（原始文本）或 fields（已解析字段）二选一。
 */
export default function FieldGrid({
  content,
  fields: fieldsProp,
  dense = false,
}: {
  content?: string;
  fields?: ParsedField[];
  dense?: boolean;
}) {
  const fields = fieldsProp ?? parseFmtText(content);
  if (fields.length === 0) return null;

  return (
    <div className={dense ? "space-y-1" : "space-y-0"}>
      {fields.map((f, i) => (
        <FieldRow key={i} field={f} dense={dense} />
      ))}
    </div>
  );
}

function FieldRow({ field, dense }: { field: ParsedField; dense: boolean }) {
  const pad = dense ? "py-1" : "py-2";
  const indent = field.depth > 0 ? { paddingLeft: `${field.depth * 14}px` } : undefined;

  if (field.label === null) {
    return (
      <div className={`${pad} text-sm leading-relaxed text-muted-foreground`} style={indent}>
        {field.value}
        <ItemList items={field.items} />
      </div>
    );
  }

  return (
    <div
      className={`flex gap-3 border-t border-border/60 first:border-t-0 ${pad}`}
      style={indent}
    >
      <span className="w-20 shrink-0 text-sm text-muted-foreground">{field.label}</span>
      <div className="min-w-0 flex-1 text-sm leading-relaxed">
        {field.value && <span>{field.value}</span>}
        <ItemList items={field.items} />
      </div>
    </div>
  );
}

function ItemList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2 text-sm leading-relaxed text-muted-foreground">
          <span className="select-none text-border">·</span>
          <span className="min-w-0 flex-1">{it}</span>
        </li>
      ))}
    </ul>
  );
}
