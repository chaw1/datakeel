import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../i18n/context";

import { Breadcrumbs } from "./Breadcrumbs";

it("renders multi-level group and ancestor trails and invokes navigate on clicks", async () => {
  const user = userEvent.setup();
  const navigate = vi.fn();

  const { rerender } = render(
    <I18nContext.Provider
      value={{ locale: "en", setLocale: vi.fn(), t: translator("en") }}
    >
      <Breadcrumbs page="datasets" navigate={navigate} />
    </I18nContext.Provider>,
  );
  expect(
    screen.getByRole("navigation", { name: "Breadcrumb" }),
  ).toBeInTheDocument();
  expect(document.querySelector(".breadcrumb-group")).toHaveTextContent("Data");
  expect(document.querySelector(".breadcrumb-current")).toHaveTextContent(
    "Data library",
  );
  await user.click(screen.getByRole("button", { name: "Workspace" }));
  expect(navigate).toHaveBeenCalledWith("workbench");

  rerender(
    <I18nContext.Provider
      value={{ locale: "en", setLocale: vi.fn(), t: translator("en") }}
    >
      <Breadcrumbs
        page="runs"
        navigate={navigate}
        params={new URLSearchParams("type=pipeline")}
      />
    </I18nContext.Provider>,
  );
  expect(document.querySelector(".breadcrumb-group")).toHaveTextContent(
    "Operations",
  );
  expect(document.querySelector(".breadcrumb-current")).toHaveTextContent(
    "Pipeline",
  );
  await user.click(screen.getByRole("button", { name: "Run records" }));
  expect(navigate).toHaveBeenCalledWith("runs");

  rerender(
    <I18nContext.Provider
      value={{ locale: "en", setLocale: vi.fn(), t: translator("en") }}
    >
      <Breadcrumbs
        page="object"
        navigate={navigate}
        objectKind="metric"
        objectName="零售额"
        objectTab="relations"
      />
    </I18nContext.Provider>,
  );
  expect(document.querySelector(".breadcrumb-kind")).toHaveTextContent(
    "Metric",
  );
  expect(document.querySelector(".breadcrumb-current")).toHaveTextContent(
    "Retail revenue",
  );
  expect(document.querySelector(".breadcrumb-tab")).toHaveTextContent(
    "Relations",
  );
  await user.click(screen.getByRole("button", { name: "Data catalog" }));
  expect(navigate).toHaveBeenCalledWith("catalog");

  rerender(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <Breadcrumbs
        page="object"
        navigate={navigate}
        objectKind="metric"
        objectName="零售额"
        objectTab="relations"
      />
    </I18nContext.Provider>,
  );
  expect(document.querySelector(".breadcrumb-current")).toHaveTextContent(
    "对象",
  );
});
