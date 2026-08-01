import type { CreditCoverageItem, CreditIssuerSummary } from "./types";

export const CREDIT_BOND_PAGE_SIZE = 20;

export function filterCreditItems(
  items: CreditCoverageItem[],
  search: string,
  status: string,
) {
  const query = search.trim().toLowerCase();
  return items.filter((item) => {
    const matchesStatus = status === "all" || item.watch_status === status;
    const target = `${item.bond_code} ${item.bond_name} ${item.normalized_issuer} ${item.rating} ${item.sector} ${item.region}`.toLowerCase();
    return matchesStatus && (!query || target.includes(query));
  });
}

export function filterCreditIssuers(items: CreditIssuerSummary[], search: string) {
  const query = search.trim().toLowerCase();
  return items.filter((issuer) =>
    !query
    || `${issuer.issuer} ${issuer.sector} ${issuer.region} ${issuer.issuer_type}`
      .toLowerCase()
      .includes(query),
  );
}

export function buildCreditImportPath(
  filename: string,
  commit: boolean,
  mapping: Record<string, string>,
) {
  const params = new URLSearchParams({ filename, commit: String(commit) });
  if (Object.keys(mapping).length) params.set("mapping", JSON.stringify(mapping));
  return `/credit/import?${params.toString()}`;
}

export function toggleCreditMember(
  current: number[],
  observationId: number,
  checked: boolean,
) {
  if (checked) return current.includes(observationId) ? current : [...current, observationId];
  return current.filter((id) => id !== observationId);
}

export function filterCreditPortfolioMembers(
  items: CreditCoverageItem[],
  search: string,
  selectedOnly: boolean,
  selectedIds: number[],
) {
  const query = search.trim().toLowerCase();
  const selected = new Set(selectedIds);
  return items.filter((item) => {
    if (selectedOnly && !selected.has(item.id)) return false;
    if (!query) return true;
    return `${item.bond_code} ${item.bond_name} ${item.normalized_issuer}`
      .toLowerCase()
      .includes(query);
  });
}

export function nextCreditVisibleCount(
  current: number,
  total: number,
  pageSize = CREDIT_BOND_PAGE_SIZE,
) {
  return Math.min(total, Math.max(pageSize, current + pageSize));
}

export function calculateCreditWorkspaceScrollTop({
  currentScrollTop,
  panelTop,
  toolbarBottom,
  gap = 12,
}: {
  currentScrollTop: number;
  panelTop: number;
  toolbarBottom: number;
  gap?: number;
}) {
  return Math.max(
    0,
    currentScrollTop + panelTop - toolbarBottom - gap,
  );
}
