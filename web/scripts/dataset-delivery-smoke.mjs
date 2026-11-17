// Use a fresh loopback Datakeel home. Run from the repository root.
// node web/scripts/dataset-delivery-smoke.mjs http://127.0.0.1:8773 artifacts/dataset-delivery
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { appearance, localBase } from "./screenshots-helpers.mjs";

const base = localBase(process.argv[2]);
assert.ok(process.argv[3], "Pass an evidence output directory");
const output = path.resolve(process.argv[3]);
const repository = fileURLToPath(new URL("../../", import.meta.url));
const fixture = path.join(output, "warehouse-images");
await mkdir(fixture, { recursive: true });

const generate = `
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def scene(label):
    image = Image.new("RGB", (320, 210), "#dce7e9")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 141, 320, 210), fill="#c6c3ad")
    if label == "pallet":
        draw.polygon(((14, 60), (207, 40), (305, 61), (305, 147), (14, 163)), fill="#a6b8bd")
        draw.polygon(((14, 60), (207, 40), (305, 61), (14, 73)), fill="#365365")
        draw.rectangle((40, 82, 133, 159), fill="#263e49")
        draw.rectangle((47, 88, 126, 125), fill="#6d8993")
        for y in range(93, 121, 8):
            draw.line((47, y, 126, y), fill="#abc1c5", width=2)
        draw.rectangle((161, 78, 248, 142), fill="#eff0e6")
        draw.rectangle((170, 86, 205, 119), fill="#4a7280")
        draw.rectangle((211, 86, 239, 119), fill="#4a7280")
        draw.rectangle((76, 154, 183, 178), fill="#724b2a")
        for x, y in ((79, 129), (115, 125), (149, 133)):
            draw.rectangle((x, y, x + 30, 155), fill="#cf9a60", outline="#9e6c40", width=2)
            draw.line((x + 15, y, x + 15, 154), fill="#eac58c", width=3)
        draw.line((198, 184, 294, 172), fill="#f6edcb", width=5)
    else:
        draw.polygon(((0, 94), (104, 51), (104, 148), (0, 166)), fill="#7c927b")
        draw.polygon(((116, 150), (251, 84), (320, 99), (320, 203)), fill="#788585")
        draw.line((193, 174, 316, 124), fill="#ece6ae", width=5)
        draw.rectangle((148, 97, 220, 151), fill="#ba812d")
        draw.rectangle((160, 65, 205, 108), outline="#233737", width=6)
        draw.rectangle((213, 80, 224, 155), fill="#263b3f")
        draw.line((223, 155, 261, 155), fill="#263b3f", width=6)
        for x in (149, 195):
            draw.ellipse((x, 137, x + 24, 162), fill="#283f43")
    return image

root = Path(sys.argv[1])
for split, name, label, bbox in (
    ("train", "loading-bay", "pallet", [76, 125, 107, 53]),
    ("test", "loading-bay-copy", "pallet", [76, 125, 107, 53]),
    ("test", "entrance", "forklift", [148, 65, 114, 98]),
):
    folder = root / split / name
    folder.mkdir(parents=True, exist_ok=True)
    scene(label).save(folder / "image.png")
    annotation = {"width": 320, "height": 210, "annotations": [{"category": label, "bbox": bbox}]}
    (folder / "annotations.json").write_text(json.dumps(annotation), encoding="utf-8")
    if label == "pallet":
        (folder / "caption.txt").write_text(f"Generated warehouse sample: {label}\\n", encoding="utf-8")
`;
execFileSync("uv", ["run", "--no-sync", "python", "-c", generate, fixture], {
  cwd: repository,
});

const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  reducedMotion: "reduce",
  acceptDownloads: true,
  serviceWorkers: "block",
});
const failures = [];
await context.route("**/*", async (route) => {
  const url = new URL(route.request().url());
  if (url.origin === base.origin) {
    await route.continue();
  } else {
    failures.push(`External request: ${url.origin}`);
    await route.abort("blockedbyclient");
  }
});
const page = await context.newPage();
page.setDefaultTimeout(25_000);
page.on("pageerror", (error) => failures.push(error.message));

async function read(route) {
  const response = await context.request.get(new URL(route, base).href, {
    maxRedirects: 0,
  });
  assert.ok(response.ok(), `${route}: ${response.status()}`);
  return response.json();
}

function region(name = "Dataset delivery review") {
  return page.getByRole("region", { name, exact: true });
}

async function checkCandidate(state) {
  const review = region();
  await review
    .getByRole("button", { name: "Check imported splits", exact: true })
    .click();
  await review.locator(`[data-delivery-status="${state}"]`).waitFor();
}

async function capture(view, filename) {
  await view.evaluate(async (element) => {
    await Promise.all(
      Array.from(element.querySelectorAll("img"), (image) => image.decode()),
    );
  });
  await view.screenshot({ path: path.join(output, filename) });
}

try {
  await page.goto(`${base.origin}/#/datasets`);
  await appearance(page, "en", "light");
  await page
    .getByRole("button", { name: "Import images", exact: true })
    .click();
  await page.getByLabel("Choose image folder").setInputFiles(fixture);
  await page.getByLabel("Dataset name").fill("Warehouse images");
  const importPanel = region("Import images");
  await importPanel.getByRole("heading", { name: "Folder preview" }).waitFor();
  await importPanel.getByText("2 with captions", { exact: true }).waitFor();
  await capture(
    importPanel.locator(".import-preview"),
    "dataset-import-en.png",
  );
  await appearance(page, "zh", "light");
  await capture(
    region("导入图片").locator(".import-preview"),
    "dataset-import-zh.png",
  );
  await appearance(page, "en", "light");
  await page
    .getByRole("button", { name: "Import dataset", exact: true })
    .click();
  await page.waitForURL(/#\/object\/dataset\/[^?]+\?tab=versions/);
  const datasetId = decodeURIComponent(
    new URL(page.url()).hash.split("/")[3].split("?")[0],
  );
  const versionsRoute = `/api/datasets/${encodeURIComponent(datasetId)}/versions`;
  const [source] = await read(versionsRoute);
  assert.equal(source.file_count, 3);
  assert.equal(
    source.manifest.filter((file) => file.metadata.split === "test").length,
    2,
  );

  await checkCandidate("blocked");
  await region().getByText("pallet", { exact: true }).first().waitFor();
  await capture(region(), "dataset-delivery-en.png");
  await appearance(page, "zh", "light");
  await capture(region(/交付审查/), "dataset-delivery-zh.png");
  await appearance(page, "en", "light");

  await region()
    .getByRole("checkbox", { name: /Exclude .*loading-bay-copy/ })
    .first()
    .check();
  await region()
    .getByRole("button", { name: "Review corrected version", exact: true })
    .click();
  await region()
    .getByRole("button", { name: "Execute action", exact: true })
    .click();
  await region()
    .getByText(/Corrected version created/)
    .waitFor();
  const versions = await read(versionsRoute);
  const corrected = versions.find((item) => item.id !== source.id);
  assert.equal(corrected?.file_count, 2);
  assert.equal(versions.find((item) => item.id === source.id)?.file_count, 3);
  assert.ok(
    corrected.manifest.every(
      (item) => !item.filename.includes("loading-bay-copy"),
    ),
  );
  await checkCandidate("ready");

  const reviewed = region();
  await reviewed
    .getByText("Sign and deliver this candidate", { exact: true })
    .click();
  await reviewed
    .getByLabel("Semantic version tag", { exact: true })
    .fill("v1.0.0");
  await reviewed
    .getByRole("button", { name: "Review release plan", exact: true })
    .click();
  const approve = reviewed.getByRole("button", {
    name: "Approve and publish release",
    exact: true,
  });
  await approve.waitFor();
  const releases = `/api/datasets/${encodeURIComponent(datasetId)}/releases`;
  assert.deepEqual(await read(releases), []);
  await approve.click();
  const download = reviewed.getByRole("button", {
    name: "Export delivery package",
    exact: true,
  });
  await download.waitFor();
  const [release] = await read(releases);
  assert.equal(release.version_id, corrected.id);
  assert.equal(release.metadata.delivery_review.baseline_version_id, source.id);
  assert.equal(release.metadata.delivery_review.sample_count, 2);
  assert.equal(release.metadata.delivery_review.leakage_pairs, 0);
  const event = page.waitForEvent("download");
  await download.click();
  const archive = path.join(output, "delivery.tar.gz");
  await (await event).saveAs(archive);
  const raw = execFileSync(
    "uv",
    [
      "run",
      "--no-sync",
      "datakeel",
      "reconcile",
      archive,
      "--manifest",
      "MANIFEST.json",
      "--json",
    ],
    {
      cwd: repository,
      env: {
        PATH: process.env.PATH,
        DATAKEEL_DATABASE_URL: "unsupported://offline",
        NO_COLOR: "1",
      },
      encoding: "utf8",
    },
  );
  const receipt = JSON.parse(raw);
  assert.equal(receipt.categories.length, 6);
  assert.ok(receipt.categories.every((category) => category.passed));
  assert.deepEqual(failures, []);
  await writeFile(
    path.join(output, "report.json"),
    JSON.stringify(
      { source: source.id, corrected: corrected.id, release, receipt },
      null,
      2,
    ),
  );
  process.stdout.write(
    "Browser import, leakage correction, human approval and offline delivery verification passed.\n",
  );
} catch (error) {
  await page.screenshot({
    path: path.join(output, "failure.png"),
    fullPage: true,
  });
  throw error;
} finally {
  await browser.close();
}
