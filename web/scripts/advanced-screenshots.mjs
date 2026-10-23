import assert from "node:assert/strict";

import { advancedFixture, advancedPrompt } from "./advanced-smoke.mjs";

export async function prepareAdvancedScreenshots(
  context,
  base,
  datasetId,
  writes,
) {
  async function post(endpoint, data) {
    assert.ok(
      ["/api/agent/conversations", "/api/agent/memories"].includes(endpoint),
    );
    if (endpoint === "/api/agent/conversations")
      assert.equal(data.provider, "fake");
    writes.push({
      method: "POST",
      url: new URL(endpoint, base).href,
      phase: "advanced-fixture",
    });
    const response = await context.request.post(new URL(endpoint, base).href, {
      data,
      maxRedirects: 0,
    });
    assert.equal(response.ok(), true, await response.text());
    return response.json();
  }
  const fixture = await advancedFixture(post, datasetId);
  const endpoint = `/api/agent/conversations/${fixture.conversation.id}/messages`;
  writes.push({
    method: "POST",
    url: new URL(endpoint, base).href,
    phase: "advanced-fixture",
  });
  const response = await context.request.post(new URL(endpoint, base).href, {
    data: {
      content: advancedPrompt,
      idempotency_key: `screenshot-${fixture.conversation.id}`,
    },
    maxRedirects: 0,
  });
  assert.equal(response.ok(), true, await response.text());
  const stream = await response.text();
  assert.match(stream, /event: done/);
  assert.match(stream, /catalog-analyst/);
  assert.match(stream, new RegExp(fixture.memory.id));
  return {
    conversationId: fixture.conversation.id,
    memoryId: fixture.memory.id,
  };
}
