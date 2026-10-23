import assert from "node:assert/strict";
import { realpathSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const defaultRoot = fileURLToPath(new URL("../src/", import.meta.url));
const colorPattern = /#[\da-f]{3,8}\b|\b(?:rgba?|hsla?)\s*\(/gi;
const tokenFiles = /^styles\/(?:tokens|palette-[\w-]+)\.css$/;
const inheritedValues = /^(?:inherit|initial|unset|revert|revert-layer)$/;
const colorProperties =
  /^(?:color|background(?:Color|Image)?|border(?:Top|Right|Bottom|Left|Block|Inline)?(?:Color)?|outline(?:Color)?|fill|stroke|(?:box|text)Shadow|(?:accent|caret|columnRule|textDecoration|stop|flood|lighting)Color)$/;
const namedColors = new Set(
  `aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen`.split(
    " ",
  ),
);

function withoutComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, (comment) =>
    comment.replace(/[^\n]/g, " "),
  );
}

function diagnostic(source, filename, offset, message) {
  const line = source.slice(0, offset).split("\n").length;
  return `${filename}:${line}: ${message}`;
}

function unwrap(node) {
  while (
    node &&
    (ts.isParenthesizedExpression(node) ||
      ts.isAsExpression(node) ||
      ts.isSatisfiesExpression(node) ||
      ts.isNonNullExpression(node))
  )
    node = node.expression;
  return node;
}

function staticText(node) {
  node = unwrap(node);
  return node &&
    (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
    ? node.text
    : undefined;
}

function hasLiteralColor(value) {
  const clean = value.replace(/url\([^)]*\)/gi, "").replace(/--[\w-]+/g, "");
  return (
    new RegExp(colorPattern.source, "i").test(clean) ||
    [...clean.matchAll(/\b[a-z]+\b/gi)].some(([word]) =>
      namedColors.has(word.toLowerCase()),
    )
  );
}

function inspectScript(source, filename) {
  const file = ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    filename.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const problems = new Set();
  const declarations = new Map();
  const visitedStyles = new Set();
  const report = (node, message) =>
    problems.add(diagnostic(source, filename, node.getStart(file), message));
  function visitStyle(input) {
    const node = unwrap(input);
    if (!node || visitedStyles.has(node)) return;
    visitedStyles.add(node);
    if (ts.isIdentifier(node)) return visitStyle(declarations.get(node.text));
    if (ts.isConditionalExpression(node)) {
      visitStyle(node.whenTrue);
      visitStyle(node.whenFalse);
    }
    if (!ts.isObjectLiteralExpression(node)) return;
    for (const property of node.properties) {
      if (ts.isSpreadAssignment(property)) {
        visitStyle(property.expression);
        continue;
      }
      if (!ts.isPropertyAssignment(property)) continue;
      const name = ts.isIdentifier(property.name)
        ? property.name.text
        : staticText(
            ts.isComputedPropertyName(property.name)
              ? property.name.expression
              : property.name,
          );
      const value = staticText(property.initializer);
      if (
        colorProperties.test(name) &&
        value !== undefined &&
        hasLiteralColor(value)
      )
        report(property.name, "Use a color token in the inline style.");
      if (
        ["fontSize", "lineHeight"].includes(name) &&
        !(value?.includes("var(--") || inheritedValues.test(value ?? ""))
      )
        report(
          property.name,
          `Use a typography token for ${name} (${property.initializer.getText(file)}).`,
        );
      visitStyle(property.initializer);
    }
  }
  function collect(node) {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer
    )
      declarations.set(node.name.text, node.initializer);
    ts.forEachChild(node, collect);
  }
  function visit(node) {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      (/styles?$/i.test(node.name.text) ||
        node.type?.getText(file).includes("CSSProperties"))
    )
      visitStyle(node.initializer);
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText(file);
      const input =
        node.initializer && ts.isJsxExpression(node.initializer)
          ? node.initializer.expression
          : node.initializer;
      if (name === "style") visitStyle(input);
      const value = staticText(input);
      if (
        ["fill", "stroke"].includes(name) &&
        value !== undefined &&
        (!/^var\(\s*--[\w-]+/.test(value) || hasLiteralColor(value))
      )
        report(node.name, "Use var(--…) in the SVG attribute.");
      else if (
        ["color", "stopColor", "floodColor", "lightingColor"].includes(name) &&
        value !== undefined &&
        hasLiteralColor(value)
      )
        report(node.name, "Use a color token in the JSX attribute.");
    }
    ts.forEachChild(node, visit);
  }
  collect(file);
  visit(file);
  return [...problems];
}

export function inspectTokenSource(source, filename) {
  const problems = [];
  const clean = withoutComments(source);
  const isCss = filename.endsWith(".css");
  if (filename.startsWith("i18n/")) {
    for (const match of source.matchAll(/[\u0100-\u024f\u1e00-\u1eff]/g))
      problems.push(
        diagnostic(
          source,
          filename,
          match.index,
          "The bundled latin font subset does not include latin-ext characters.",
        ),
      );
  }
  if (isCss && source.trimEnd().split("\n").length > 600) {
    problems.push(
      `${filename}:1: CSS file exceeds 600 lines; split by feature.`,
    );
  }
  if (isCss && tokenFiles.test(filename)) return problems;
  if (!isCss) return [...problems, ...inspectScript(source, filename)];
  for (const match of clean.matchAll(colorPattern)) {
    problems.push(
      diagnostic(
        source,
        filename,
        match.index,
        "Use a color token, not a literal.",
      ),
    );
  }
  const typography = /\b(font-size|line-height)\s*:\s*([^;}]+)/gi;
  for (const match of clean.matchAll(typography)) {
    const value = match[2].trim().replace(/\s*!important$/, "");
    if (value.includes("var(--") || inheritedValues.test(value)) continue;
    problems.push(
      diagnostic(
        source,
        filename,
        match.index,
        `Use a typography token for ${match[1]} (${value}).`,
      ),
    );
  }
  return problems;
}

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const groups = await Promise.all(
    entries.map(async (entry) => {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) return sourceFiles(path);
      return /\.(?:css|tsx?)$/.test(entry.name) &&
        !/\.test\.[^.]+$/.test(entry.name) &&
        entry.name !== "generated.ts"
        ? [path]
        : [];
    }),
  );
  return groups.flat();
}

export async function checkTokens(root = defaultRoot) {
  const files = await sourceFiles(root);
  const results = await Promise.all(
    files.map(async (path) =>
      inspectTokenSource(
        await readFile(path, "utf8"),
        relative(root, path).replaceAll("\\", "/"),
      ),
    ),
  );
  return results.flat();
}

function selfTest() {
  assert.equal(
    inspectTokenSource('export const title = "Ā";', "i18n/fixture.ts").length,
    1,
  );
  assert.equal(
    inspectTokenSource('export const title = "中文 · Café";', "i18n/fixture.ts")
      .length,
    0,
  );
  const filename = "features/evidence/fixture.css";
  const negative = inspectTokenSource(
    ".row {\n  color: #123456;\n}\n",
    filename,
  );
  assert.deepEqual(negative, [
    `${filename}:2: Use a color token, not a literal.`,
  ]);
  assert.equal(
    inspectTokenSource("a { color: rgb(1 2 3); }", filename).length,
    1,
  );
  assert.equal(
    inspectTokenSource("a { color: hsl(0 0% 0%); }", filename).length,
    1,
  );
  assert.equal(
    inspectTokenSource("a { font-size: 13px; line-height: 1.45; }", filename)
      .length,
    2,
  );
  assert.equal(inspectTokenSource(".row {}\n".repeat(601), filename).length, 1);
  assert.deepEqual(
    inspectTokenSource(
      "/* color: #123456; */\na { color: var(--ink); font-size: var(--font-sm); line-height: var(--line-table); }",
      filename,
    ),
    [],
  );
  assert.deepEqual(
    inspectTokenSource(
      ":root { --ink: #123456; }",
      "styles/palette-pencil.css",
    ),
    [],
  );
  assert.equal(
    inspectTokenSource(":root { --ink: #123456; }", "features/tokens.css")
      .length,
    1,
  );
  assert.equal(
    inspectTokenSource('<path stroke="#123456" />', "features/graph/Card.tsx")
      .length,
    1,
  );
  assert.equal(
    inspectTokenSource(
      'const style = { color: "#123456", fontSize: 13 };',
      "a.tsx",
    ).length,
    2,
  );
  const jsxFile = "features/graph/ColorFixture.tsx";
  for (const literal of [
    '<path stroke="#123456" />',
    "<path stroke='#123456' />",
    '<path stroke={"#123456"} />',
    "<path stroke={'#123456'} />",
    "<path stroke={`#123456`} />",
    '<path fill="red" />',
    '<path fill={"rebeccapurple"} />',
    "<path fill={`blue`} />",
    '<path fill="none" />',
    '<path stroke="currentColor" />',
    '<path stroke="var(--ink, red)" />',
    '<div style={{ color: "red" }} />',
    "<div style={{ color: `#123456` }} />",
    '<div style={{ backgroundColor: "rgb(1 2 3)" }} />',
    '<div style={{ borderColor: "hsl(20 30% 40%)" }} />',
    '<div style={{ border: "1px solid red" }} />',
    '<div style={{ boxShadow: "0 0 2px RebeccaPurple" }} />',
    '<div style={{ ["color"]: "red" }} />',
    'const props = { color: "red" }; const node = <div style={props} />;',
    'const props: React.CSSProperties = { color: "red" };',
  ]) {
    const problems = inspectTokenSource(
      `// unchanged line\n${literal}`,
      jsxFile,
    );
    assert.equal(problems.length, 1, literal);
    assert.ok(problems[0].startsWith(`${jsxFile}:2:`), literal);
  }
  assert.deepEqual(
    inspectTokenSource(
      `
    // <path stroke={"#123456"} />
    /* <div style={{ color: "red", fontSize: 12 }} /> */
    const text = 'fill="red" stroke={"#123456"} color: "blue"';
    const url = "https://example.invalid/*red*/#123456";
    const node = <p>fill="red" fontSize: 12</p>;
    const good = <svg fill="var(--icon-fill)" stroke={"var(--icon-stroke)"} />;
    const style = { color: "var(--red)", fontSize: "var(--font-sm)", lineHeight: "inherit", backgroundImage: 'url("red.png")' };
  `,
      jsxFile,
    ),
    [],
  );
  process.stdout.write(
    `Token gate self-test passed: injected #123456 rejected at ${filename}:2; JSX quotes/expressions/templates, named/hex/RGB/HSL inline colors, comment/text exclusions, typography, and file-size cases passed.\n`,
  );
}

if (
  process.argv[1] &&
  realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))
) {
  if (process.argv.includes("--self-test")) selfTest();
  else {
    const problems = await checkTokens();
    process.stdout.write(
      problems.length
        ? `${problems.join("\n")}\n`
        : "Style token gate passed (colors, typography, and CSS file sizes).\n",
    );
    process.exitCode = problems.length ? 1 : 0;
  }
}
