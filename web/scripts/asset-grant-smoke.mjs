import assert from "node:assert/strict";

// The demo publishes request and restricted metric cards without hidden grants. Ask
// candidates disclose those metrics, so the smoke first checks the refusal, then applies
// as the Ask operator (the API's default actor) and approves through the controlled
// action, whose reviewer is a different person.
const ASK_OPERATOR = "local-user";

export async function grantProtectedDemoMetrics({ page, json, post, checks }) {
  const ask = new URL("/api/ask", page.url()).href;
  const refused = await page.request.post(ask, {
    data: { question: "退货率为什么上升" },
  });
  assert.equal(refused.status(), 403);
  assert.match((await refused.json()).detail, /apply for access/);
  const market = await json("/api/data-assets?limit=50");
  const protectedCards = market.items
    .map((item) => item.asset)
    .filter(
      (asset) =>
        asset.definition.target.asset_type === "metric" &&
        ["request", "restricted"].includes(asset.definition.classification),
    );
  assert.ok(protectedCards.length >= 2);
  const granted = [];
  for (const asset of protectedCards) {
    const application = await post(
      `/api/data-assets/${asset.id}/applications`,
      {
        applicant: ASK_OPERATOR,
        purpose: "UI smoke: enterprise questions that list this metric",
        scopes: ["query"],
        expires_at: "2030-01-01T00:00:00Z",
      },
    );
    const plan = await post("/api/actions/decide_asset_application/prepare", {
      application_id: application.id,
      approve: true,
      reason: "UI smoke reviewer",
    });
    assert.equal(plan.reversible, false);
    await post(`/api/approvals/${plan.id}`, {
      approve: true,
      plan_digest: plan.plan_digest,
    });
    const run = await post(`/api/actions/${plan.id}/execute`, {
      plan_digest: plan.plan_digest,
    });
    assert.equal(run.status, "SUCCEEDED");
    granted.push(asset.definition.target.asset_id);
  }
  checks.push(
    `protected candidate metrics refuse Ask with an apply hint until ${ASK_OPERATOR} holds approved query grants (${granted.join(", ")})`,
  );
  return granted;
}
