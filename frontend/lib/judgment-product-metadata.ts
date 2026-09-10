import type { JudgmentBProductMetadata } from "@/lib/api/types";
import type { PerBProduct } from "@/lib/result-format";

function normalizeTitle(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

function productIdFromUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    const host = url.hostname.toLocaleLowerCase().replace(/^www\./, "");
    const parts = url.pathname.split("/").filter(Boolean);
    if (host === "walmart.com") {
      const ipIndex = parts.indexOf("ip");
      const tail = ipIndex >= 0 ? parts.slice(ipIndex + 1) : [];
      return [...tail].reverse().find((part) => /^\d+$/.test(part));
    }
    if (host === "amazon.com") {
      const marker = parts.findIndex((part) => part === "dp" || part === "gp");
      const candidate = marker >= 0 && parts[marker] === "gp" && parts[marker + 1] === "product"
        ? parts[marker + 2]
        : marker >= 0
          ? parts[marker + 1]
          : undefined;
      return candidate && /^[A-Z0-9]{10}$/i.test(candidate) ? candidate : undefined;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function applyMetadata(
  product: PerBProduct,
  metadata: JudgmentBProductMetadata,
): PerBProduct {
  return {
    ...product,
    productId: metadata.product_id || undefined,
    productUrl: metadata.product_url || undefined,
    productImage: metadata.product_image || undefined,
  };
}

export function resolveJudgmentProducts(
  products: PerBProduct[],
  metadata: JudgmentBProductMetadata[] | undefined,
  bUrls: string[] | undefined,
): PerBProduct[] {
  if (metadata?.length) {
    const byTitle = new Map<string, JudgmentBProductMetadata[]>();
    for (const item of metadata) {
      const key = normalizeTitle(item.title);
      byTitle.set(key, [...(byTitle.get(key) ?? []), item]);
    }
    return products.map((product) => {
      const matches = byTitle.get(normalizeTitle(product.name)) ?? [];
      return matches.length === 1 ? applyMetadata(product, matches[0]) : product;
    });
  }

  if (!bUrls || bUrls.length !== products.length) return products;
  return products.map((product, index) => ({
    ...product,
    productId: productIdFromUrl(bUrls[index]),
    productUrl: bUrls[index],
  }));
}
