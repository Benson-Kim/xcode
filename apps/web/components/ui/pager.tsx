"use client";

import { useId, useState } from "react";

import { useFormats } from "../../lib/formats";
import { cn } from "./cn";
import { ChevronIcon, ChevronsLeftIcon } from "./icons";
import { SearchSelect } from "./search-select";

export const PAGE_SIZES: readonly number[] = [25, 50, 100];
export const DEFAULT_PAGE_SIZE = PAGE_SIZES[0];

export type PageItem = number | "gap";

// The page buttons: the first and last page and the two either side of the current one, with an ellipsis for
// each stretch left out (1 … 4 5 [6] 7 8 … 25). A stretch of one page is shown rather than hidden.
export function pageItems(page: number, pages: number): PageItem[] {
  const wanted = new Set([1, pages]);
  for (let at = page - 2; at <= page + 2; at++)
    if (at >= 1 && at <= pages) wanted.add(at);
  const shown = [...wanted].sort((a, b) => a - b);
  const items: PageItem[] = [];
  shown.forEach((at, index) => {
    const before = shown[index - 1];
    if (before !== undefined && at - before === 2) items.push(before + 1);
    else if (before !== undefined && at - before > 2) items.push("gap");
    items.push(at);
  });
  return items;
}

export const pageCount = (total: number, pageSize: number) =>
  Math.max(1, Math.ceil(total / pageSize));

// The page shown and its size. The page goes back to 1 whenever the size or the filters (anything in filterKey)
// change, and stepBack(total) moves it to the last page that exists when the list has shrunk under it.
export function usePaging(filterKey: string, defaultSize = DEFAULT_PAGE_SIZE) {
  const [pageSize, setPageSize] = useState(defaultSize);
  const key = `${filterKey}|${pageSize}`;
  const [at, setAt] = useState({ key, page: 1 });
  const page = at.key === key ? at.page : 1;
  return {
    page,
    pageSize,
    setPage: (next: number) => setAt({ key, page: next }),
    setPageSize,
    stepBack(total: number) {
      const last = pageCount(total, pageSize);
      if (page > last) setAt({ key, page: last });
    },
  };
}

const NAV_BUTTON =
  "grid h-11 min-w-11 place-items-center rounded-[10px] border border-line bg-surface px-2 text-[15px] font-semibold text-navy hover:enabled:border-blue hover:enabled:text-blue-dark disabled:cursor-default disabled:opacity-35 aria-[current=page]:border-blue aria-[current=page]:bg-blue-soft aria-[current=page]:text-blue-dark";

// The Pager under a list read a server page at a time (usePagedList).
export function ListPager({
  list,
}: {
  list: { total: number; paging: ReturnType<typeof usePaging> };
}) {
  return (
    <Pager
      page={list.paging.page}
      pageSize={list.paging.pageSize}
      total={list.total}
      onPageChange={list.paging.setPage}
      onPageSizeChange={list.paging.setPageSize}
    />
  );
}

// Under a list, in a bar like the toolbar's: the rows per page on the left, "Showing 51–100 of 1,234" in the middle
// and the page buttons on the right. Nothing shows while everything fits the smallest page size; one page shows
// only the size and the count.
export function Pager({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  sizes = PAGE_SIZES,
  className,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  sizes?: readonly number[];
  className?: string;
}) {
  const { formatNumber } = useFormats();
  const sizeId = useId();
  if (total <= Math.min(...sizes)) return null;

  const pages = pageCount(total, pageSize);
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const go = (to: number) => () => onPageChange(to);
  const choices = (
    sizes.includes(pageSize)
      ? [...sizes]
      : [...sizes, pageSize].sort((a, b) => a - b)
  ).map((size) => ({ value: String(size), label: String(size) }));

  return (
    <div
      className={cn(
        "mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 rounded-[14px] border border-card-line bg-surface p-3 max-[720px]:flex-col max-[720px]:items-stretch max-[720px]:text-center",
        className,
      )}
    >
      <div className="flex items-center gap-2 max-[720px]:justify-center">
        <label htmlFor={sizeId} className="text-sm text-grey">
          Rows per page
        </label>
        <SearchSelect
          id={sizeId}
          density="compact"
          inline
          className="w-24!"
          options={choices}
          value={String(pageSize)}
          onChange={(size) => onPageSizeChange(Number(size))}
        />
      </div>
      <p className="m-0 text-sm text-grey" aria-live="polite">
        Showing {formatNumber(first)}–{formatNumber(last)} of{" "}
        {formatNumber(total)}
      </p>
      {pages > 1 ? (
        <nav
          aria-label="Pages"
          className="flex flex-wrap items-center gap-1.5 max-[720px]:justify-center"
        >
          <button
            type="button"
            aria-label="First page"
            className={NAV_BUTTON}
            disabled={page <= 1}
            onClick={go(1)}
          >
            <ChevronsLeftIcon />
          </button>
          <button
            type="button"
            aria-label="Previous page"
            className={NAV_BUTTON}
            disabled={page <= 1}
            onClick={go(page - 1)}
          >
            <ChevronIcon size={20} className="rotate-90" />
          </button>
          {pageItems(page, pages).map((item, index) =>
            item === "gap" ? (
              <span key={`gap${index}`} aria-hidden="true" className="px-1">
                …
              </span>
            ) : (
              <button
                key={item}
                type="button"
                aria-label={`Page ${item}`}
                aria-current={item === page ? "page" : undefined}
                className={NAV_BUTTON}
                onClick={go(item)}
              >
                {formatNumber(item)}
              </button>
            ),
          )}
          <button
            type="button"
            aria-label="Next page"
            className={NAV_BUTTON}
            disabled={page >= pages}
            onClick={go(page + 1)}
          >
            <ChevronIcon size={20} className="-rotate-90" />
          </button>
          <button
            type="button"
            aria-label="Last page"
            className={NAV_BUTTON}
            disabled={page >= pages}
            onClick={go(pages)}
          >
            <ChevronsLeftIcon className="rotate-180" />
          </button>
        </nav>
      ) : (
        <span aria-hidden="true" />
      )}
    </div>
  );
}
