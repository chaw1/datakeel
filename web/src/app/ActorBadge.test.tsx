import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../i18n/context";

import { ActorBadge } from "./ActorBadge";
import { useActorIdentity } from "./useActorIdentity";

it("renders local, admin, scoped, and read-only role summaries", () => {
  const cases = [
    {
      identity: { actor: "local", zeroUsers: true, scopes: ["*"] },
      expected: "Actor local · Local mode",
    },
    {
      identity: {
        actor: "alice",
        zeroUsers: false,
        scopes: ["manage_users", "save_metadata"],
      },
      expected: "Actor alice · Administrator",
    },
    {
      identity: {
        actor: "reviewer",
        zeroUsers: false,
        scopes: ["production:annotate", "production:review"],
      },
      expected: "Actor reviewer · 2 scopes",
    },
    {
      identity: { actor: "guest", zeroUsers: false, scopes: [] },
      expected: "Actor guest · Read-only",
    },
  ] as const;

  for (const { identity, expected } of cases) {
    const { unmount } = render(
      <I18nContext.Provider
        value={{ locale: "en", setLocale: vi.fn(), t: translator("en") }}
      >
        <ActorBadge identity={identity} />
      </I18nContext.Provider>,
    );
    expect(screen.getByLabelText(expected)).toBeVisible();
    expect(screen.getByText(identity.actor)).toBeVisible();
    unmount();
  }
});

it("loads identity from /api/production/workbench and falls back safely offline", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            actor: "steward",
            zero_users: false,
            effective_scopes: {
              actor: "steward",
              scopes: ["define_role"],
              zero_users: false,
            },
            projects: [],
          }),
        ),
      ),
    ),
  );
  const { result } = renderHook(() => useActorIdentity());
  await waitFor(() => {
    expect(result.current).toEqual({
      actor: "steward",
      zeroUsers: false,
      scopes: ["define_role"],
    });
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("offline"))),
  );
  const offline = renderHook(() => useActorIdentity());
  expect(offline.result.current.actor).toBe("local");
  expect(offline.result.current.zeroUsers).toBe(true);
});
