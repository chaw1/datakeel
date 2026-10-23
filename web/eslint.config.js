import { fixupPluginRules } from "@eslint/compat";
import js from "@eslint/js";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

import project from "./scripts/eslint-project.mjs";

export default tseslint.config(
  { ignores: ["node_modules/**", "src/api/generated.ts", "public/**"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    files: ["src/**/*.{ts,tsx}", "scripts/**/*.d.mts", "vite.config.ts"],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "jsx-a11y": fixupPluginRules(jsxA11y),
      import: importPlugin,
    },
    settings: {
      "import/resolver": { typescript: { project: "./tsconfig.json" } },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "import/order": [
        "error",
        {
          groups: [
            "builtin",
            "external",
            "internal",
            "parent",
            "sibling",
            "index",
            "type",
          ],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "max-lines": ["error", { max: 400 }],
    },
  },
  {
    files: ["src/**/*.tsx"],
    plugins: { project },
    rules: {
      "max-lines": ["error", { max: 300 }],
      "project/single-component-export": "error",
      "project/localized-ui-text": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXText[value=/[\u3400-\u4dbf\u4e00-\u9fff]/]",
          message: "Keep Chinese UI text in the centralized locale catalog.",
        },
      ],
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}"],
    rules: { "max-lines": ["error", { max: 600 }] },
  },
  {
    files: ["**/*.js", "**/*.mjs"],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: { process: "readonly", URL: "readonly" } },
  },
);
