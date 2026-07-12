import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // CommonJS Express shim (revisited in T-040); require() is correct here.
    "server.js",
  ]),
  {
    // Permissive start: the prototype dashboard/chat components are rebuilt in
    // R1 (T-063) and R3 (agent). Keep these rules as warnings so lint still
    // surfaces them without blocking CI on soon-to-be-replaced code.
    rules: {
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);

export default eslintConfig;
