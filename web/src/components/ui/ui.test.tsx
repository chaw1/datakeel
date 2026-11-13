import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  Badge,
  Button,
  EmptyState,
  Input,
  PageHeader,
  SegmentedTabs,
  Select,
  Surface,
} from "./index";

it("renders Button variants, sizes, default type, icons, and disabled state", async () => {
  const user = userEvent.setup();
  const onClick = vi.fn();
  render(
    <>
      <Button onClick={onClick} icon="refresh">
        {"Refresh"}
      </Button>
      <Button variant="primary" size="lg" type="submit">
        {"Submit"}
      </Button>
      <Button variant="danger" size="sm" disabled>
        {"Delete"}
      </Button>
      <Button variant="ghost">{"Ghost"}</Button>
      <Button variant="link">{"Link"}</Button>
    </>,
  );
  const refresh = screen.getByRole("button", { name: "Refresh" });
  expect(refresh).toHaveAttribute("type", "button");
  expect(refresh.querySelector("svg")).not.toBeNull();
  await user.click(refresh);
  expect(onClick).toHaveBeenCalledTimes(1);

  const submit = screen.getByRole("button", { name: "Submit" });
  expect(submit).toHaveAttribute("type", "submit");
  expect(submit).toHaveClass("ui-button-primary", "ui-button-lg");

  const del = screen.getByRole("button", { name: "Delete" });
  expect(del).toBeDisabled();
  expect(del).toHaveClass("ui-button-danger", "ui-button-sm");

  expect(screen.getByRole("button", { name: "Ghost" })).toHaveClass(
    "ui-button-ghost",
  );
  expect(screen.getByRole("button", { name: "Link" })).toHaveClass(
    "text-button",
    "ui-button-link",
  );
});

it("renders Select and forwards selection changes", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <Select
      size="sm"
      aria-label={"Scope"}
      defaultValue="all"
      onChange={onChange}
    >
      <option value="all">{"All"}</option>
      <option value="active">{"Active"}</option>
    </Select>,
  );
  const select = screen.getByRole("combobox", { name: "Scope" });
  expect(select).toHaveClass("ui-select", "ui-select-sm");
  await user.selectOptions(select, "active");
  expect(onChange).toHaveBeenCalled();
});

it("renders plain and icon-adorned Input primitives", async () => {
  const user = userEvent.setup();
  render(
    <>
      <Input aria-label={"Plain"} mono placeholder={"id"} />
      <Input icon="search" aria-label={"Search"} placeholder={"find"} />
    </>,
  );
  const plain = screen.getByRole("textbox", { name: "Plain" });
  expect(plain).toHaveClass("ui-input", "ui-mono");
  const search = screen.getByRole("textbox", { name: "Search" });
  expect(search.closest(".ui-input-field")).not.toBeNull();
  expect(
    search.closest(".ui-input-field")?.querySelector("svg"),
  ).not.toBeNull();
  await user.type(search, "demo");
  expect(search).toHaveValue("demo");
});

it("renders Badge tones and optional status dot", () => {
  const { container } = render(
    <>
      <Badge tone="ok" dot>
        {"Ready"}
      </Badge>
      <Badge tone="stamp" mono>
        {"Irreversible"}
      </Badge>
    </>,
  );
  expect(screen.getByText("Ready")).toHaveClass(
    "badge",
    "green",
    "ui-badge-ok",
  );
  expect(container.querySelector(".status-dot")).not.toBeNull();
  expect(screen.getByText("Irreversible")).toHaveClass(
    "badge",
    "red",
    "ui-badge-stamp",
    "ui-mono",
  );
});

it("renders Surface, PageHeader, SegmentedTabs, and EmptyState", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(
    <Surface as="section" variant="ledger" aria-label={"Ledger"}>
      <PageHeader
        eyebrow={"Archive"}
        title={"Records"}
        subtitle={"Summary"}
        compact
        actions={<Button size="sm">{"Action"}</Button>}
      />
      <SegmentedTabs
        label={"Views"}
        activeId="facts"
        onSelect={onSelect}
        items={[
          { id: "facts", label: "Facts", count: 4 },
          { id: "history", label: "History" },
        ]}
      />
      <EmptyState
        icon="database"
        title={"Nothing yet"}
        description={"No rows"}
        card
        action={<Button>{"Reload"}</Button>}
      />
    </Surface>,
  );
  const region = screen.getByRole("region", { name: "Ledger" });
  expect(region).toHaveClass("card", "ui-surface", "ui-surface-ledger");
  expect(
    screen.getByRole("heading", { level: 1, name: "Records" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: /Facts/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await user.click(screen.getByRole("button", { name: "History" }));
  expect(onSelect).toHaveBeenCalledWith("history");
  expect(screen.getByText("Nothing yet").closest(".ui-empty")).toHaveClass(
    "card",
    "empty-state",
  );
});
