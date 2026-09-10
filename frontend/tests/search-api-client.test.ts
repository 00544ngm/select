import { afterEach, expect, it, vi } from "vitest";
import { searchWalmart } from "@/lib/api/search";

afterEach(() => vi.restoreAllMocks());

it("posts the exact keyword to the existing search route", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        results: [
          {
            title: "Mat",
            url: "https://walmart.com/ip/1",
            price: "$9",
            rating: "",
            review_count: "",
            image: "",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )
  );

  const response = await searchWalmart("pizza cutting board non slip");

  expect(response.results[0].title).toBe("Mat");
  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:8000/api/v1/search",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ keyword: "pizza cutting board non slip" }),
    })
  );
});
