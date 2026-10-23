import { useId, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { filterValue, serializeFilterValue } from "./values";

import type { MetricFilter } from "../../api/catalog";

const operations = [
  ["eq", "catEqual"],
  ["ne", "catNotEqual"],
  ["in", "catOneOf"],
  ["gte", "catAtLeast"],
  ["lte", "catAtMost"],
] as const;

export function MetricFilters({
  filters,
  table,
  onChange,
}: {
  filters: MetricFilter[];
  table: string;
  onChange: (filters: MetricFilter[]) => void;
}) {
  const { t } = useI18n();
  const id = useId();
  const [rawValues, setRawValues] = useState<Record<number, string>>({});
  function update(index: number, value: MetricFilter) {
    onChange(
      filters.map((filter, position) => (position === index ? value : filter)),
    );
  }
  return (
    <fieldset className="catalog-filter-editor">
      <legend>{t("catFilters")}</legend>
      <p className="small muted">{t("catFilterHelp")}</p>
      {filters.map((filter, index) => (
        <div className="catalog-filter-row" key={`${id}-${String(index)}`}>
          <label htmlFor={`${id}-column-${String(index)}`}>
            {t("catFilterColumn")}
            <input
              id={`${id}-column-${String(index)}`}
              required
              value={filter.column}
              onChange={(event) => {
                update(index, { ...filter, column: event.target.value });
              }}
            />
          </label>
          <label htmlFor={`${id}-op-${String(index)}`}>
            {t("catFilterOperator")}
            <select
              id={`${id}-op-${String(index)}`}
              value={filter.op}
              onBlur={(event) => {
                const operation = operations.find(
                  ([value]) => value === event.target.value,
                )?.[0];
                if (operation && operation !== filter.op)
                  update(index, {
                    ...filter,
                    op: operation,
                    value:
                      operation === "in"
                        ? [filter.value].flat()
                        : ([filter.value].flat()[0] ?? ""),
                  });
              }}
              onChange={(event) => {
                const operation = operations.find(
                  ([value]) => value === event.target.value,
                )?.[0];
                if (operation)
                  update(index, {
                    ...filter,
                    op: operation,
                    value:
                      operation === "in"
                        ? Array.isArray(filter.value)
                          ? filter.value
                          : [filter.value]
                        : Array.isArray(filter.value)
                          ? (filter.value[0] ?? "")
                          : filter.value,
                  });
              }}
            >
              {operations.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={`${id}-value-${String(index)}`}>
            {t("catFilterValue")}
            <input
              id={`${id}-value-${String(index)}`}
              value={rawValues[index] ?? serializeFilterValue(filter.value)}
              onChange={(event) => {
                const value = event.target.value;
                setRawValues({ ...rawValues, [index]: value });
                update(index, {
                  ...filter,
                  value:
                    filter.op === "in"
                      ? value.split(",").map(filterValue)
                      : filterValue(value),
                });
              }}
            />
          </label>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setRawValues({});
              onChange(filters.filter((_, position) => position !== index));
            }}
          >
            {t("catRemoveFilter")}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button subtle"
        onClick={() => {
          onChange([...filters, { column: `${table}/`, op: "eq", value: "" }]);
        }}
      >
        {t("catAddFilter")}
      </button>
    </fieldset>
  );
}
