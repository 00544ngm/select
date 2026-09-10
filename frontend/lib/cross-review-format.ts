export type CrossReviewBlock = {
  kind: "heading" | "list" | "text";
  raw: string;
};

export type CrossReviewInline =
  | { kind: "text"; value: string }
  | { kind: "strong"; value: string };

export type CrossReviewDocumentBlock =
  | { kind: "heading"; level: number; content: CrossReviewInline[] }
  | { kind: "paragraph"; content: CrossReviewInline[] }
  | { kind: "unordered-list"; items: CrossReviewInline[][] }
  | { kind: "ordered-list"; items: CrossReviewInline[][] }
  | {
      kind: "table";
      headers: CrossReviewInline[][];
      rows: CrossReviewInline[][][];
    };

function lineKind(raw: string): CrossReviewBlock["kind"] {
  const line = raw.replace(/(?:\r\n|\r|\n)$/, "");
  if (/^\s*(?:#{1,6}\s+|\d+[.)、]\s+|[一二三四五六七八九十]+[、.]\s*)/.test(line)) {
    return "heading";
  }
  if (/^\s*(?:[-*+]\s+|[•·▪◦]\s*)/.test(line)) {
    return "list";
  }
  return "text";
}

export function formatCrossReview(raw: string): CrossReviewBlock[] {
  if (!raw) return [];
  const lines = raw.match(/[^\r\n]*(?:(?:\r\n)|\r|\n|$)/g) ?? [];
  return lines
    .filter((line) => line.length > 0)
    .map((line) => ({ kind: lineKind(line), raw: line }));
}

export function joinCrossReviewBlocks(blocks: CrossReviewBlock[]): string {
  return blocks.map((block) => block.raw).join("");
}

function parseInline(value: string): CrossReviewInline[] {
  const nodes: CrossReviewInline[] = [];
  const pattern = /\*\*([^*\n]+)\*\*/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      nodes.push({ kind: "text", value: value.slice(cursor, index) });
    }
    nodes.push({ kind: "strong", value: match[1] });
    cursor = index + match[0].length;
  }
  if (cursor < value.length) {
    nodes.push({ kind: "text", value: value.slice(cursor) });
  }
  return nodes.length ? nodes : [{ kind: "text", value }];
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string, columns: number): boolean {
  const cells = splitTableRow(line);
  return (
    columns >= 2 &&
    cells.length === columns &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell))
  );
}

function headingMatch(line: string): RegExpMatchArray | null {
  return line.match(/^\s*(#{1,6})\s+(.+?)\s*$/);
}

function unorderedListMatch(line: string): RegExpMatchArray | null {
  return line.match(/^\s*(?:[-*+]|[•·▪◦])\s+(.+?)\s*$/);
}

function orderedListMatch(line: string): RegExpMatchArray | null {
  return line.match(/^\s*\d+(?:[.)、])\s+(.+?)\s*$/);
}

function beginsStructuredBlock(lines: string[], index: number): boolean {
  const line = lines[index] ?? "";
  if (headingMatch(line) || unorderedListMatch(line) || orderedListMatch(line)) {
    return true;
  }
  const cells = splitTableRow(line);
  return line.includes("|") && isTableSeparator(lines[index + 1] ?? "", cells.length);
}

export function parseCrossReviewMarkdown(
  raw: string
): CrossReviewDocumentBlock[] {
  if (!raw) return [];
  const lines = raw.replace(/\r\n?/g, "\n").split("\n");
  const blocks: CrossReviewDocumentBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    if (!lines[index].trim()) {
      index += 1;
      continue;
    }

    const heading = headingMatch(lines[index]);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        content: parseInline(heading[2]),
      });
      index += 1;
      continue;
    }

    const unordered = unorderedListMatch(lines[index]);
    if (unordered) {
      const items: CrossReviewInline[][] = [];
      while (index < lines.length) {
        const item = unorderedListMatch(lines[index]);
        if (!item) break;
        items.push(parseInline(item[1]));
        index += 1;
      }
      blocks.push({ kind: "unordered-list", items });
      continue;
    }

    const ordered = orderedListMatch(lines[index]);
    if (ordered) {
      const items: CrossReviewInline[][] = [];
      while (index < lines.length) {
        const item = orderedListMatch(lines[index]);
        if (!item) break;
        items.push(parseInline(item[1]));
        index += 1;
      }
      blocks.push({ kind: "ordered-list", items });
      continue;
    }

    const headerCells = splitTableRow(lines[index]);
    if (
      lines[index].includes("|") &&
      isTableSeparator(lines[index + 1] ?? "", headerCells.length)
    ) {
      index += 2;
      const rows: CrossReviewInline[][][] = [];
      while (index < lines.length && lines[index].includes("|")) {
        const row = splitTableRow(lines[index]);
        if (row.length !== headerCells.length) break;
        rows.push(row.map(parseInline));
        index += 1;
      }
      blocks.push({
        kind: "table",
        headers: headerCells.map(parseInline),
        rows,
      });
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      (paragraphLines.length === 0 || !beginsStructuredBlock(lines, index))
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push({
      kind: "paragraph",
      content: parseInline(paragraphLines.join("\n")),
    });
  }

  return blocks;
}
