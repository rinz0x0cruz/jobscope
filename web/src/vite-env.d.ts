/// <reference types="vite/client" />

// dashboard.json is baked in at build time by Vite's JSON handling. Typed as
// `unknown` here (then cast via lib/schema) so tsc never has to infer the huge
// literal type of the emitted payload.
declare module '*.json' {
  const value: unknown
  export default value
}
