import assert from "node:assert/strict";
import { URLSearchParams } from "node:url";

import { appearance, settle } from "./screenshots-helpers.mjs";

async function graphLayout(page) {
  const scroll = page.locator(".graph-scroll");
  const measure = await scroll.evaluate((element) => {
    const boundary = element.getBoundingClientRect();
    const cards = [...element.querySelectorAll(".archive-card-button")];
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      right: boundary.right,
      lastRight: Math.max(
        ...cards.map((card) => card.getBoundingClientRect().right),
      ),
    };
  });
  if (measure.lastRight > measure.right + 1) {
    const hint = page.locator(".graph-scroll-hint");
    assert.equal(
      await hint.isVisible(),
      true,
      "Clipped graph has a visible scroll hint",
    );
    await hint.getByRole("button").last().click();
    await page.waitForFunction(() => {
      const element = globalThis.document.querySelector(".graph-scroll");
      return (
        element.scrollLeft + element.clientWidth >= element.scrollWidth - 2
      );
    });
    await scroll.evaluate((element) => {
      element.scrollLeft = 0;
    });
  }
  return measure;
}

export async function refinementSmoke({ page, json, screenshot, checks }) {
  const origin = new URL(page.url()).origin;
  const datasets = await json("/api/datasets?include=quality");
  const paired = datasets.find((item) => item.metadata.evidence_samples);
  assert.ok(paired);
  const files = await json(`/api/datasets/${paired.id}/files`);
  const file = files.find(
    (item) => item.filename === "val/scene-0817/image.png",
  );
  assert.ok(file);
  await page.setViewportSize({ width: 1440, height: 900 });
  const graphEvidence = [];
  for (const locale of ["zh", "en"]) {
    for (const [kind, id] of [
      ["metric", "retail_revenue"],
      ["file", file.id],
    ]) {
      const query = new URLSearchParams({
        tab: "relations",
        dataset: paired.id,
      });
      await page.goto(
        `${origin}/#/object/${kind}/${encodeURIComponent(id)}?${query}`,
      );
      await page.locator(".archive-card-button").first().waitFor();
      await appearance(page, locale, "light");
      await settle(page);
      const cards = await page
        .locator(".archive-card-button")
        .evaluateAll((elements) =>
          elements.map((element) => ({
            kind: element.dataset.assetType,
            name: element.querySelector(".archive-name").textContent.trim(),
            prefix: element.querySelector(".archive-prefix")?.textContent ?? "",
          })),
        );
      const columns = await page
        .locator(".graph-column-title")
        .allTextContents();
      const counter = await page.locator(".graph-toolbar").innerText();
      assert.doesNotMatch(counter, /·\s*·/);
      if (locale === "zh") {
        assert.ok(!columns.includes("task"));
        assert.ok(cards.every((card) => card.name !== "Pipeline run"));
        assert.match(counter, /\d+ 个资产 · \d+ 条关系边/);
        assert.ok(
          (await page.locator(".event-meta .badge").allTextContents()).every(
            (status) =>
              !/\b(?:COMPLETED|SUCCEEDED|RUNNING|FAIL)\b/.test(status),
          ),
          "Event status badges are localized while raw event codes stay in details",
        );
      }
      if (kind === "metric") {
        assert.ok(
          cards.some(
            (card) =>
              card.name === (locale === "zh" ? "零售额" : "Retail revenue"),
          ),
        );
        assert.ok(
          cards
            .filter((card) => card.kind === "term")
            .every((card) => !card.name.startsWith("term/")),
        );
        const dates = cards.filter(
          (card) => card.kind === "column" && card.name.endsWith(".date"),
        );
        assert.ok(
          dates.length >= 2,
          "Metric relations expose two distinct date columns",
        );
        assert.equal(
          new Set(dates.map((card) => card.name)).size,
          dates.length,
        );
        assert.ok(dates.every((card) => card.prefix.endsWith(".")));
      } else {
        const neighbors = cards.filter((card) => card.kind === "file");
        assert.ok(neighbors.length > 0);
        assert.ok(
          neighbors.every(
            (card) => card.name !== "file" && card.name !== "文件",
          ),
        );
        assert.ok(
          neighbors.some((card) => card.name === "scene-0817/image.png"),
        );
        assert.ok(neighbors.every((card) => !card.name.startsWith("val/")));
      }
      const layout = await graphLayout(page);
      await screenshot(`p5_1-${kind}-${locale}-1440`, false);
      graphEvidence.push({ kind, locale, cards, columns, counter, layout });
    }
  }
  checks.push(
    "F1/F2/F3/F6: bilingual metric/file cards have readable names, unique table-qualified dates, single separators, translated task labels and actionable overflow hints at 1440x900",
  );

  await page.goto(`${origin}/#/workbench`);
  await page.locator(".workbench-section").first().waitFor();
  const approvals = await json("/api/approvals?status=pending");
  const tasks = await json("/api/tasks");
  const attention =
    approvals.length +
    tasks.filter((task) =>
      ["PENDING", "QUEUED", "RUNNING"].includes(task.state),
    ).length +
    datasets.filter(
      (item) => item.quality_score != null && item.quality_score < 60,
    ).length;
  for (const locale of ["en", "zh"]) {
    await appearance(page, locale, "light");
    await page
      .getByRole("heading", {
        name:
          locale === "zh"
            ? `工作台 · ${attention} 项待处理`
            : `Workbench · ${attention} need attention`,
        exact: true,
      })
      .waitFor();
  }
  checks.push(
    "F3: workbench attention total matches pending approvals + running pipelines + low-quality datasets in both languages",
  );

  await page.goto(`${origin}/#/evidence`);
  await page.locator(".dataset-selector select").selectOption(paired.id);
  await page.locator(".assertion-matrix").first().waitFor();
  await settle(page);
  const sourceOrder = await page
    .locator(".assertion-matrix")
    .first()
    .locator("thead a")
    .evaluateAll((elements) =>
      elements.map((element) => ({
        marker: element.textContent,
        target: element.hash.slice(1),
      })),
    );
  assert.deepEqual(
    sourceOrder.map((item) => item.marker),
    ["a", "b", "c"],
  );
  for (const item of sourceOrder) {
    const marker = await page
      .locator(`[id="${item.target}"] .footnote-marker`)
      .textContent();
    assert.equal(marker, item.marker);
  }
  checks.push(
    "F4: evidence matrix a/b/c columns match the deduplicated footer sources",
  );

  await page.goto(`${origin}/#/ask`);
  await page.locator("#ask-question").fill("上个季度华东区零售额是多少");
  await page.locator(".ask-composer button[type=submit]").click();
  await page.locator(".ask-answer-heading time").waitFor();
  const reference = await page
    .locator(".ask-answer-heading time")
    .textContent();
  assert.equal(reference, "10-01 00:00 UTC");
  assert.equal(
    await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    "Asia/Shanghai",
  );
  checks.push(
    "F5: Ask reference time remains 10-01 00:00 UTC in a browser using Asia/Shanghai",
  );
  await appearance(page, "en", "light");
  return { graphEvidence, attention, sourceOrder, reference };
}
