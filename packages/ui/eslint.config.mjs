import tseslint from "typescript-eslint";

export default [
  { ignores: ["node_modules/**"] },
  ...tseslint.configs.recommended,
];
