import assert from "node:assert/strict";
import { realpathSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const paletteRoot = fileURLToPath(new URL("../src/styles/", import.meta.url));
const backgrounds = ["paper", "sheet"];
const foregrounds = {
  ink: 7,
  muted: 4.5,
  pencil: 4.5,
  red: 4.5,
  ok: 4.5,
  warn: 4.5,
  // Annotation label colors: shape strokes on the canvas and text on label chips.
  ...Object.fromEntries(
    Array.from({ length: 8 }, (_, index) => [
      `label-${String(index + 1)}`,
      4.5,
    ]),
  ),
};
const requiredTokens = [
  ...backgrounds,
  ...Object.keys(foregrounds),
  "rule",
  "pencil-wash",
];
const themePatterns = {
  light: /(?:^|})\s*:root\s*\{([^}]+)\}/m,
  dark: /:root\[data-theme=["']dark["']\]\s*\{([^}]+)\}/,
  system:
    /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root:not\(\[data-theme=["']light["']\]\)\s*\{([^}]+)\}/,
};

function luminance(hex) {
  let color = hex.replace("#", "");
  if (color.length === 3)
    color = [...color].map((digit) => digit + digit).join("");
  const values = color.match(/../g).map((value) => {
    const channel = parseInt(value, 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
}

export function contrastRatio(foreground, background) {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function parseTheme(source, theme) {
  const body = source.match(themePatterns[theme])?.[1];
  if (!body) throw new Error(`Missing ${theme} theme selector.`);
  const values = Object.fromEntries(
    [...body.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)].map((match) => [
      match[1],
      match[2].trim().toLowerCase(),
    ]),
  );
  for (const token of requiredTokens) {
    if (!/^#(?:[\da-f]{3}|[\da-f]{6})$/.test(values[token] ?? "")) {
      throw new Error(`${theme}: --${token} must declare an opaque hex color.`);
    }
  }
  return values;
}

export function inspectPalette(source, filename) {
  const problems = [];
  const measurements = [];
  const clean = source.replace(/\/\*[\s\S]*?\*\//g, "");
  try {
    const themes = Object.fromEntries(
      Object.keys(themePatterns).map((name) => [name, parseTheme(clean, name)]),
    );
    for (const token of requiredTokens) {
      if (themes.dark[token] !== themes.system[token]) {
        problems.push(
          `${filename}: system dark --${token} differs from explicit dark.`,
        );
      }
    }
    for (const theme of ["light", "dark"]) {
      const colors = themes[theme];
      for (const [foreground, minimum] of Object.entries(foregrounds)) {
        const ratios = backgrounds.map((background) => {
          const ratio = contrastRatio(colors[foreground], colors[background]);
          if (ratio < minimum) {
            problems.push(
              `${filename}: ${theme} --${foreground}/--${background} ${ratio.toFixed(3)}:1 < ${minimum}:1`,
            );
          }
          return `--${background} ${ratio.toFixed(3)}:1`;
        });
        measurements.push(
          `${filename} ${theme} --${foreground}: ${ratios.join(", ")} (minimum ${minimum}:1)`,
        );
      }
    }
  } catch (error) {
    problems.push(`${filename}: ${error.message}`);
  }
  return { problems, measurements };
}

export async function checkContrast(directory = paletteRoot) {
  const files = (await readdir(directory)).filter((name) =>
    /^palette-[\w-]+\.css$/.test(name),
  );
  if (files.length === 0) throw new Error("No palette CSS files found.");
  const results = await Promise.all(
    files
      .sort()
      .map(async (name) =>
        inspectPalette(await readFile(resolve(directory, name), "utf8"), name),
      ),
  );
  return {
    problems: results.flatMap((result) => result.problems),
    measurements: results.flatMap((result) => result.measurements),
  };
}

function fixture(lightMuted = "#000000") {
  const values = (background, foreground, muted) =>
    requiredTokens
      .map((token) => {
        const color = backgrounds.includes(token)
          ? background
          : token === "muted"
            ? muted
            : foreground;
        return `--${token}: ${color};`;
      })
      .join("\n");
  const light = values("#ffffff", "#000000", lightMuted);
  const dark = values("#000000", "#ffffff", "#ffffff");
  return `:root { ${light} }\n:root[data-theme="dark"] { ${dark} }\n@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ${dark} } }`;
}

function selfTest() {
  assert.equal(contrastRatio("#000", "#fff"), 21);
  assert.equal(contrastRatio("#fff", "#000"), 21);
  assert.equal(contrastRatio("#777", "#777"), 1);
  assert.ok(contrastRatio("#777777", "#ffffff") < 4.5);
  assert.deepEqual(inspectPalette(fixture(), "fixture.css").problems, []);
  const negative = inspectPalette(fixture("#AAAAAA"), "fixture.css");
  assert.equal(negative.problems.length, 2);
  assert.match(
    negative.problems[0],
    /light --muted\/--paper 2\.323:1 < 4\.5:1/,
  );
  assert.match(
    inspectPalette(fixture().split("@media")[0], "fixture.css").problems[0],
    /Missing system theme selector/,
  );
  assert.match(
    inspectPalette(
      fixture().replace(
        /--muted: #ffffff;(?![\s\S]*--muted)/,
        "--muted: #eeeeee;",
      ),
      "fixture.css",
    ).problems[0],
    /system dark --muted differs/,
  );
  process.stdout.write(
    `Contrast gate self-test passed: injected --muted: #AAAAAA rejected (${negative.problems.join("; ")}); WCAG reference values and dark-theme completeness passed.\n`,
  );
}

if (
  process.argv[1] &&
  realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))
) {
  if (process.argv.includes("--self-test")) selfTest();
  else {
    const result = await checkContrast();
    process.stdout.write(`${result.measurements.join("\n")}\n`);
    process.stdout.write(
      result.problems.length
        ? `${result.problems.join("\n")}\n`
        : "Palette contrast gate passed; explicit and system dark themes agree.\n",
    );
    process.exitCode = result.problems.length ? 1 : 0;
  }
}
