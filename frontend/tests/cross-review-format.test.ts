import { expect, it } from "vitest";
import {
  formatCrossReview,
  joinCrossReviewBlocks,
  parseCrossReviewMarkdown,
} from "@/lib/cross-review-format";

it("preserves every original character while grouping blocks", () => {
  const raw = "结论\n1. 优点\n原始说明\n\n- 风险一\n- 风险二";
  const blocks = formatCrossReview(raw);

  expect(joinCrossReviewBlocks(blocks)).toBe(raw);
  expect(blocks.some((block) => block.kind === "heading")).toBe(true);
  expect(blocks.some((block) => block.kind === "list")).toBe(true);
});

it("falls back to one text block for unstructured content", () => {
  const raw = "没有结构但必须原样保留";

  expect(formatCrossReview(raw)).toEqual([{ kind: "text", raw }]);
});

it("preserves Windows line endings, spaces, and trailing newlines", () => {
  const raw = "## 标题  \r\n  正文不裁剪 \r\n• 项目\r\n";

  expect(joinCrossReviewBlocks(formatCrossReview(raw))).toBe(raw);
});

it("parses headings paragraphs lists emphasis and tables into document blocks", () => {
  const raw = [
    "## 合理之处",
    "",
    "正文包含 **评论证据**。",
    "",
    "- 结实耐用",
    "- 便于携带",
    "",
    "1. 先核对规格",
    "2. 再验证需求",
    "",
    "| 搭配方向 | 判断 |",
    "| --- | --- |",
    "| 笔 | 合理 |",
  ].join("\n");

  const document = parseCrossReviewMarkdown(raw);

  expect(document.map((block) => block.kind)).toEqual([
    "heading",
    "paragraph",
    "unordered-list",
    "ordered-list",
    "table",
  ]);
  expect(document[0]).toMatchObject({ kind: "heading", level: 2 });
  expect(document[1]).toMatchObject({
    kind: "paragraph",
    content: [
      { kind: "text", value: "正文包含 " },
      { kind: "strong", value: "评论证据" },
      { kind: "text", value: "。" },
    ],
  });
  expect(document[4]).toMatchObject({
    kind: "table",
    headers: [
      [{ kind: "text", value: "搭配方向" }],
      [{ kind: "text", value: "判断" }],
    ],
  });
});

it("keeps malformed table syntax as readable paragraph text", () => {
  const document = parseCrossReviewMarkdown("| 只有一行 |\n普通正文");

  expect(document).toHaveLength(1);
  expect(document[0]).toMatchObject({ kind: "paragraph" });
});

it("treats html and unmatched emphasis as plain text", () => {
  const document = parseCrossReviewMarkdown(
    "<script>alert('x')</script>\n\n**没有闭合"
  );

  expect(document).toEqual([
    {
      kind: "paragraph",
      content: [{ kind: "text", value: "<script>alert('x')</script>" }],
    },
    {
      kind: "paragraph",
      content: [{ kind: "text", value: "**没有闭合" }],
    },
  ]);
});
