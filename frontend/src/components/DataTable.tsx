import { useMemo, useState } from "react";

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  value?: (row: T) => string | number;
  sortable?: boolean;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  filterPlaceholder?: string;
  filterValue?: (row: T) => string;
  rowClassName?: (row: T) => string;
  emptyMessage?: string;
}

type SortDir = "asc" | "desc";

/**
 * Shared data table: client-side sort + text filter.
 * Used by every list view in the portal.
 */
export default function DataTable<T extends object>({
  columns,
  rows,
  filterPlaceholder = "Filter…",
  filterValue,
  rowClassName,
  emptyMessage = "Nothing to show.",
}: Props<T>) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const cellValue = (col: Column<T>, row: T): string | number => {
    if (col.value) return col.value(row);
    const v = (row as Record<string, unknown>)[col.key];
    if (v === null || v === undefined) return "";
    if (typeof v === "number") return v;
    return String(v);
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      (filterValue ? filterValue(r) : JSON.stringify(r)).toLowerCase().includes(q),
    );
  }, [rows, query, filterValue]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return filtered;
    return [...filtered].sort((a, b) => {
      const va = cellValue(col, a);
      const vb = cellValue(col, b);
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb));
      return sortDir === "asc" ? cmp : -cmp;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, sortKey, sortDir, columns]);

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  return (
    <div className="data-table">
      <div className="data-table-toolbar">
        <input
          className="input"
          placeholder={filterPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">
          {sorted.length} of {rows.length}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>
                {c.sortable !== false ? (
                  <button className="th-sort" onClick={() => toggleSort(c.key)}>
                    {c.label}
                    {sortKey === c.key && (sortDir === "asc" ? " ▲" : " ▼")}
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="muted center">
                {emptyMessage}
              </td>
            </tr>
          )}
          {sorted.map((row, i) => (
            <tr key={i} className={rowClassName ? rowClassName(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(row) : String(cellValue(c, row))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
