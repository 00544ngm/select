import type { ProviderModelOption } from "./api/types";

export type ModelCatalogFilter = "all" | "recent" | "verified";
export type ModelCatalogSort = "smart" | "recent" | "usage" | "verified" | "name";

export interface ModelCatalogView {
  query: string;
  filter: ModelCatalogFilter;
  sort: ModelCatalogSort;
}

function time(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function byName(a: ProviderModelOption, b: ProviderModelOption): number {
  return a.model.localeCompare(b.model, undefined, { numeric: true });
}

function byRecent(a: ProviderModelOption, b: ProviderModelOption): number {
  return time(b.last_used_at) - time(a.last_used_at) || byName(a, b);
}

function byVerified(a: ProviderModelOption, b: ProviderModelOption): number {
  const aVerified = a.test_status === "verified" && a.is_current_connection !== false;
  const bVerified = b.test_status === "verified" && b.is_current_connection !== false;
  return (
    Number(bVerified) - Number(aVerified) ||
    time(b.tested_at) - time(a.tested_at) ||
    byName(a, b)
  );
}

function bySmart(a: ProviderModelOption, b: ProviderModelOption): number {
  const aUsed = Boolean(a.last_used_at);
  const bUsed = Boolean(b.last_used_at);
  const aVerified = a.test_status === "verified" && a.is_current_connection !== false;
  const bVerified = b.test_status === "verified" && b.is_current_connection !== false;
  return (
    Number(Boolean(b.is_selected)) - Number(Boolean(a.is_selected)) ||
    Number(bUsed) - Number(aUsed) ||
    (aUsed && bUsed ? byRecent(a, b) : 0) ||
    Number(bVerified) - Number(aVerified) ||
    time(b.tested_at) - time(a.tested_at) ||
    byName(a, b)
  );
}

export function recentModelOptions(
  options: ProviderModelOption[],
  limit = 10
): ProviderModelOption[] {
  return options.filter((option) => Boolean(option.last_used_at)).sort(byRecent).slice(0, limit);
}

export function filterAndSortModelCatalog(
  options: ProviderModelOption[],
  view: ModelCatalogView
): ProviderModelOption[] {
  const query = view.query.trim().toLocaleLowerCase();
  let result = options.filter(
    (option) => !query || option.model.toLocaleLowerCase().includes(query)
  );

  if (view.filter === "recent") {
    result = result.filter((option) => Boolean(option.last_used_at));
  } else if (view.filter === "verified") {
    result = result.filter(
      (option) => option.test_status === "verified" && option.is_current_connection !== false
    );
  }

  const sorter =
    view.sort === "recent"
      ? byRecent
      : view.sort === "usage"
        ? (a: ProviderModelOption, b: ProviderModelOption) =>
            (b.use_count ?? 0) - (a.use_count ?? 0) || byRecent(a, b)
        : view.sort === "verified"
          ? byVerified
          : view.sort === "name"
            ? byName
            : bySmart;

  return [...result].sort(sorter);
}
