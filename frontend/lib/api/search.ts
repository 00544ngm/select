import { apiFetch } from "./client";
import type { SearchResponse } from "./types";

export function searchWalmart(keyword: string): Promise<SearchResponse> {
  return apiFetch<SearchResponse>("/search", {
    method: "POST",
    body: { keyword },
  });
}
