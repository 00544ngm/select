"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search, Check, ExternalLink, ShoppingCart, Loader2 } from "lucide-react";
import { searchWalmart } from "@/lib/api/search";
import { ApiError } from "@/lib/api/client";

interface SearchResult {
  title: string;
  url: string;
  price: string;
  rating: string;
  review_count: string;
  image: string;
}

interface SearchFormProps {
  onSelectB?: (urls: string[]) => void;
}

export default function SearchForm({ onSelectB }: SearchFormProps) {
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const search = useMutation({
    mutationFn: async () => (await searchWalmart(keyword.trim())).results,
  });
  const requiresBrowser =
    search.error instanceof ApiError &&
    search.error.code === "WALMART_SEARCH_REQUIRES_BROWSER";

  const toggle = (url: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  };

  const handleSelectB = () => {
    const urls = Array.from(selected);
    if (urls.length > 0 && onSelectB) {
      onSelectB(urls);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !search.isPending && search.mutate()}
          placeholder="输入商品关键词搜索Walmart"
          className="flex-1 rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus:border-foreground"
        />
        <button
          type="button"
          onClick={() => search.mutate()}
          disabled={!keyword.trim() || search.isPending}
          className="inline-flex items-center gap-1 rounded-md bg-foreground px-4 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {search.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          搜索
        </button>
      </div>

      {search.isError && (
        <div className="space-y-2 text-xs text-destructive" role="alert">
          <p>{search.error instanceof Error ? search.error.message : "搜索失败"}</p>
          {requiresBrowser && (
            <a
              href={`https://www.walmart.com/search?q=${encodeURIComponent(keyword.trim())}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium underline underline-offset-2"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              在浏览器打开 Walmart 搜索
            </a>
          )}
        </div>
      )}

      {search.data && search.data.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">未找到相关商品</p>
      )}

      {search.data && search.data.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">找到 {search.data.length} 个商品</p>
            {selected.size > 0 && (
              <button
                type="button"
                onClick={handleSelectB}
                className="inline-flex items-center gap-1 text-xs font-medium text-foreground"
              >
                <ShoppingCart className="h-3.5 w-3.5" />
                选中的 {selected.size} 个作为B商品
              </button>
            )}
          </div>
          <div className="grid gap-2">
            {search.data.map((item, i) => (
              <div
                key={item.url}
                className={`flex items-start gap-3 rounded-md border p-3 transition-colors cursor-pointer ${
                  selected.has(item.url) ? "border-foreground bg-muted" : "hover:bg-muted/50"
                }`}
                onClick={() => toggle(item.url)}
                role="option"
                aria-selected={selected.has(item.url)}
              >
                {item.image && (
                  <img
                    src={item.image}
                    alt=""
                    className="h-16 w-16 flex-shrink-0 rounded object-cover"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{item.title}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    {item.price && <span>{item.price}</span>}
                    {item.rating && <span>⭐ {item.rating}</span>}
                    {item.review_count && <span>({item.review_count})</span>}
                  </div>
                  <p className="mt-1 break-all text-xs text-muted-foreground/60">{item.url}</p>
                </div>
                <div className="flex flex-col items-center gap-1">
                  {selected.has(item.url) ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-foreground text-background">
                      <Check className="h-3 w-3" />
                    </span>
                  ) : (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border" />
                  )}
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
