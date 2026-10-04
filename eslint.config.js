import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["**/dist/**", "**/node_modules/**", "**/.venv/**", "**/test-results/**", ".playwright-mcp/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.mjs", "**/*.config.{js,ts}", "scripts/**"],
    languageOptions: { globals: { console: "readonly", process: "readonly" } },
  },
);
