import { Fragment, type ReactNode } from "react";
import {
  parseCrossReviewMarkdown,
  type CrossReviewInline,
} from "@/lib/cross-review-format";

interface CrossReviewDocumentProps {
  raw?: string;
}

export function CrossReviewDocument({ raw }: CrossReviewDocumentProps) {
  if (!raw) return null;

  const blocks = parseCrossReviewMarkdown(raw);

  return (
    <article className="space-y-4 text-sm leading-7 text-foreground/85">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return (
            <DocumentHeading key={index} level={block.level}>
              <InlineContent content={block.content} />
            </DocumentHeading>
          );
        }

        if (block.kind === "paragraph") {
          return (
            <p key={index} className="whitespace-pre-line">
              <InlineContent content={block.content} />
            </p>
          );
        }

        if (block.kind === "unordered-list") {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineContent content={item} />
                </li>
              ))}
            </ul>
          );
        }

        if (block.kind === "ordered-list") {
          return (
            <ol key={index} className="list-decimal space-y-1 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineContent content={item} />
                </li>
              ))}
            </ol>
          );
        }

        return (
          <div key={index} className="overflow-x-auto rounded-md border">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead className="bg-muted/50">
                <tr>
                  {block.headers.map((header, cellIndex) => (
                    <th
                      key={cellIndex}
                      scope="col"
                      className="px-3 py-2 font-semibold text-foreground"
                    >
                      <InlineContent content={header} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-t">
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex} className="px-3 py-2 align-top">
                        <InlineContent content={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </article>
  );
}

function InlineContent({ content }: { content: CrossReviewInline[] }) {
  return content.map((node, index) =>
    node.kind === "strong" ? (
      <strong key={index} className="font-semibold text-foreground">
        {node.value}
      </strong>
    ) : (
      <Fragment key={index}>{node.value}</Fragment>
    )
  );
}

function DocumentHeading({
  level,
  children,
}: {
  level: number;
  children: ReactNode;
}) {
  const primaryClassName =
    "border-b pb-2 font-semibold leading-tight text-foreground";
  const secondaryClassName = "font-semibold leading-tight text-foreground";

  switch (level) {
    case 1:
      return <h1 className={`${primaryClassName} text-xl`}>{children}</h1>;
    case 2:
      return <h2 className={`${primaryClassName} text-lg`}>{children}</h2>;
    case 3:
      return <h3 className={`${secondaryClassName} text-base`}>{children}</h3>;
    case 4:
      return <h4 className={secondaryClassName}>{children}</h4>;
    case 5:
      return <h5 className={secondaryClassName}>{children}</h5>;
    default:
      return <h6 className={secondaryClassName}>{children}</h6>;
  }
}
