import tseslint from "typescript-eslint";

export default [
  { ignores: ["node_modules/**", "src/generated/**"] },
  ...tseslint.configs.recommended,
];
