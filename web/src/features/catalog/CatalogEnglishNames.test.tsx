import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { detail } from "./fixtures";
import { TableDetails } from "./TableDetails";

import type { Locale } from "../../i18n/context";

it.each(["en", "zh"] as const)(
  "prefers declared directory English names and preserves missing-name fallback in %s",
  async (locale: Locale) => {
    const translated = {
      ...detail,
      table: {
        ...detail.table,
        name: "订单目录",
        english_name: "Orders archive",
      },
      owners: [
        {
          ...detail.table,
          name: "运营负责人",
          english_name: "Operations owner",
        },
        { ...detail.table, name: "备用负责人" },
      ],
      columns: [
        {
          ...detail.columns[0],
          name: "交易额",
          english_name: "Trading amount",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(translated)))),
    );
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <TableDetails
          tableId={detail.table.asset_ref.asset_id}
          onOpenReceipt={vi.fn()}
        />
      </I18nContext.Provider>,
    );
    expect(
      await screen.findByRole("heading", {
        name: locale === "en" ? "Orders archive" : "订单目录",
      }),
    ).toBeVisible();
    expect(
      screen.getByText(
        locale === "en"
          ? "Operations owner, 备用负责人"
          : "运营负责人, 备用负责人",
        { exact: false },
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("link", {
        name: locale === "en" ? "Trading amount" : "交易额",
      }),
    ).toBeVisible();
  },
);
