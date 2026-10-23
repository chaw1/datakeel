import assert from "node:assert/strict";

export const advancedMemory =
  "Catalog lineage review should include metric dependencies.";
export const advancedPrompt = "Delegate catalog lineage review.";

export async function advancedFixture(post, datasetId) {
  const conversation = await post("/api/agent/conversations", {
    dataset_id: datasetId,
    provider: "fake",
    model: "fake-demo",
    max_turns: 12,
    max_output_tokens: 1024,
    budget: {
      conversation_tokens: 1000000,
      daily_tokens: 10000000,
      conversation_usd: "10",
      daily_usd: "100",
    },
  });
  const memory = await post("/api/agent/memories", {
    content: advancedMemory,
    dataset_id: datasetId,
    source_conversation_id: conversation.id,
  });
  return { conversation, memory };
}

export async function advancedSmoke({
  page,
  base,
  json,
  post,
  send,
  screenshot,
  checks,
  datasetId,
}) {
  const fixture = await advancedFixture(post, datasetId);
  await page.goto(`${base.origin}/#/memory`);
  await page.locator(`[data-memory-id="${fixture.memory.id}"]`).waitFor();
  await page
    .getByRole("combobox", { name: "Filter memory by dataset" })
    .selectOption(datasetId);
  const memoryCard = page.locator(`[data-memory-id="${fixture.memory.id}"]`);
  assert.equal(await memoryCard.isVisible(), true);
  assert.equal(
    await memoryCard.getByRole("link").getAttribute("href"),
    `#/agent?conversation=${fixture.conversation.id}`,
  );
  await page
    .getByRole("textbox", { name: "Memory content" })
    .fill("A manually added global review reminder.");
  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/agent/memories" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Add memory", exact: true }).click();
  const added = await (await saved).json();
  assert.equal(added.dataset_id, null);
  await page
    .getByRole("combobox", { name: "Filter memory by dataset" })
    .selectOption("all");
  await page.locator(`[data-memory-id="${added.id}"]`).waitFor();
  await screenshot("memory-en");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await page.getByRole("heading", { name: /^记忆 ·/ }).waitFor();
  await screenshot("memory-zh");
  await page
    .getByRole("combobox", { name: "语言", exact: true })
    .selectOption("en");
  await page
    .locator(`[data-memory-id="${fixture.memory.id}"]`)
    .getByRole("link")
    .click();
  const stream = await send(advancedPrompt);
  assert.match(stream, /catalog-analyst/);
  const step = page.locator(".delegation-step").first();
  await step.waitFor();
  assert.equal(await step.getAttribute("open"), null);
  await step.locator("summary").first().click();
  await step.getByText("Tools used:", { exact: false }).waitFor();
  assert.match(await step.innerText(), /list_datasets/);
  assert.match(await step.innerText(), /\d+ tokens/i);
  await page.locator(`[data-used-memory-id="${fixture.memory.id}"]`).waitFor();
  const tree = await json(
    `/api/agent/conversations/${fixture.conversation.id}/tree`,
  );
  assert.ok(
    tree.nodes.some(
      (node) => node.agent_name === "catalog-analyst" && node.tokens > 0,
    ),
  );
  await screenshot("agent-delegation-memory-en");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await screenshot("agent-delegation-memory-zh");
  await page
    .getByRole("combobox", { name: "语言", exact: true })
    .selectOption("en");
  await page.getByRole("link", { name: "Manage memories" }).click();
  const card = page.locator(`[data-memory-id="${fixture.memory.id}"]`);
  await card
    .getByRole("button", { name: "Delete memory", exact: true })
    .click();
  assert.ok(
    (await json("/api/agent/memories")).some(
      (memory) => memory.id === fixture.memory.id,
    ),
  );
  await card.getByRole("button", { name: "Keep memory" }).click();
  await card
    .getByRole("button", { name: "Delete memory", exact: true })
    .click();
  const deleted = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/agent/memories/${fixture.memory.id}` &&
      response.request().method() === "DELETE",
  );
  await card.getByRole("button", { name: "Confirm deletion" }).click();
  assert.equal((await deleted).status(), 200);
  await card.waitFor({ state: "detached" });
  await page.goto(
    `${base.origin}/#/agent?conversation=${fixture.conversation.id}`,
  );
  await send(advancedPrompt);
  const restored = await json(
    `/api/agent/conversations/${fixture.conversation.id}`,
  );
  const done = restored.events.filter(
    (event) => event.event === "done" && event.agent_path === "main",
  );
  assert.ok(!done.at(-1).used_memory_ids.includes(fixture.memory.id));
  await page
    .getByText(`Deleted memory (${fixture.memory.id})`, { exact: true })
    .waitFor();
  checks.push(
    "real memory add, exact dataset filter, source conversation link, confirmation/cancellation, hard delete and subsequent retrieval exclusion",
  );
  checks.push(
    "real serial delegated Agent steps collapse, name tools/token usage, root conversation tree, retrieved memory references and zh/en",
  );
  const canaryFixture = {
    ...fixture.conversation,
    id: "canary-ui-fixture",
    messages: [
      {
        role: "user",
        content: "Demonstrate protected-response handling",
        tool_calls: [],
      },
    ],
    events: [
      {
        id: "canary-stop",
        event: "stopped",
        agent_path: "main",
        agent_name: "main",
        tokens: 0,
        stop_reason: "canary_leak",
        text: "UI_FIXTURE_PROTECTED_CONTENT",
      },
      {
        id: "canary-done",
        event: "done",
        agent_path: "main",
        agent_name: "main",
        tokens: 0,
      },
    ],
  };
  const route = "**/api/agent/conversations/canary-ui-fixture";
  await page.route(route, (request) =>
    request.fulfill({ json: canaryFixture }),
  );
  await page.goto(`${base.origin}/#/agent?conversation=canary-ui-fixture`);
  await page.getByText(/A protected session marker appeared/).waitFor();
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /UI_FIXTURE_PROTECTED_CONTENT/,
  );
  await screenshot("agent-canary-stop-en");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await page.getByText(/模型回复中出现了受保护的会话标记/).waitFor();
  await screenshot("agent-canary-stop-zh");
  await page
    .getByRole("combobox", { name: "语言", exact: true })
    .selectOption("en");
  await page.unroute(route);
  checks.push(
    "synthetic saved-event canary UI fixture: safe explanation in zh/en and attached protected content never rendered",
  );
  return {
    conversationId: fixture.conversation.id,
    memoryId: fixture.memory.id,
    manuallyAddedId: added.id,
    nodes: tree.nodes.length,
    canaryPresentation: "synthetic saved-event UI fixture",
  };
}
