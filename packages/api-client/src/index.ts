// The typed client. Everything under src/generated/ comes from openapi.json through
// `pnpm --filter @sk/api-client generate` and is never edited by hand.
export type { components, operations, paths } from "./generated/schema";