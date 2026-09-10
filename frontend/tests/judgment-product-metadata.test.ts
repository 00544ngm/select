import { describe, expect, it } from "vitest";
import { resolveJudgmentProducts } from "@/lib/judgment-product-metadata";
import type { PerBProduct } from "@/lib/result-format";

const product = (name: string): PerBProduct => ({ name, sections: [] });

describe("resolveJudgmentProducts", () => {
  it("matches new metadata by normalized unique title", () => {
    const result = resolveJudgmentProducts(
      [product("Auxiliary One")],
      [{
        title: "  auxiliary   one ",
        product_id: "111",
        product_url: "https://www.walmart.com/ip/auxiliary-one/111",
        product_image: "https://images.example/auxiliary-one.jpg",
      }],
      undefined,
    );
    expect(result[0]).toMatchObject({
      productId: "111",
      productUrl: "https://www.walmart.com/ip/auxiliary-one/111",
      productImage: "https://images.example/auxiliary-one.jpg",
    });
  });

  it("does not borrow identity from ambiguous duplicate titles", () => {
    const result = resolveJudgmentProducts(
      [product("Same Title")],
      [
        { title: "Same Title", product_id: "1", product_image: "one.jpg" },
        { title: "same title", product_id: "2", product_image: "two.jpg" },
      ],
      undefined,
    );
    expect(result[0].productId).toBeUndefined();
    expect(result[0].productImage).toBeUndefined();
  });

  it("extracts Walmart and Amazon ids from aligned legacy urls", () => {
    const result = resolveJudgmentProducts(
      [product("One"), product("Two")],
      undefined,
      [
        "https://www.walmart.com/ip/one/123456789",
        "https://www.amazon.com/dp/B0AUX22222",
      ],
    );
    expect(result.map((item) => item.productId)).toEqual(["123456789", "B0AUX22222"]);
    expect(result.every((item) => item.productImage === undefined)).toBe(true);
  });

  it("does not align legacy urls when counts differ", () => {
    const result = resolveJudgmentProducts(
      [product("One"), product("Two")],
      undefined,
      ["https://www.walmart.com/ip/one/123456789"],
    );
    expect(result.every((item) => item.productId === undefined)).toBe(true);
  });
});
