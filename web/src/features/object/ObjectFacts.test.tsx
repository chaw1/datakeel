import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionRun } from "../../test/actionFixtures";

import { ObjectFacts } from "./ObjectFacts";
import { objectData } from "./testFixtures";

it.each([
  ["zh", "SUCCEEDED", "回执 成功"],
  ["zh", "FAILED", "回执 失败"],
  ["zh", "DENIED", "回执 拒绝执行"],
  ["en", "SUCCEEDED", "Receipt Succeeded"],
] as const)("localizes the %s receipt fact for %s", (locale, status, name) => {
  const target = { kind: "action_run", id: actionRun.id } as const;
  render(
    <I18nContext.Provider
      value={{ locale, setLocale: () => undefined, t: translator(locale) }}
    >
      <ObjectFacts
        target={target}
        data={{ ...objectData, target, action: { ...actionRun, status } }}
      />
    </I18nContext.Provider>,
  );
  expect(screen.getByRole("link", { name })).toHaveAttribute(
    "href",
    expect.stringContaining("event=receipt-1"),
  );
  expect(screen.queryByText(status, { exact: true })).not.toBeInTheDocument();
});
