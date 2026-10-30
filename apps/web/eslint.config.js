import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts", "playwright-report", "test-results"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  {
    // docs/46 §4.8: the trace module is pure TypeScript and imports no UI code
    files: ["src/trace/**/*.ts"],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [
          { group: ["react", "react-*", "@mantine/*", "@monaco-editor/*", "monaco-editor", "@tanstack/*"], message: "src/trace must not import UI code (docs/46 §4.8)" },
          { group: ["../features/*", "../ui/*", "../api/*", "**/features/**", "**/ui/**"], message: "src/trace must not import app code (docs/46 §4.8)" },
        ],
      }],
    },
  },
);
