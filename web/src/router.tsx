import { createRootRoute, createRoute, createRouter, createHashHistory, stripSearchParams } from '@tanstack/react-router'
import App from './App'
import { searchSchema, SEARCH_DEFAULTS } from './lib/urlState'

// Root validates the URL search params (hash-based so it works from file:// and the
// GitHub Pages subpath). The whole dashboard is one route; "tabs" and filters are
// just search-param state, which keeps every view shareable and back/forward-able.
const rootRoute = createRootRoute({
  validateSearch: (search: Record<string, unknown>) => searchSchema.parse(search),
  // Keep the URL clean: params equal to their defaults are dropped, so a fresh
  // visit stays at #/ instead of #/?tab=all&q=&resume=%5B%5D&...
  search: { middlewares: [stripSearchParams(SEARCH_DEFAULTS)] },
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: App,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute]),
  history: createHashHistory(),
  defaultPreload: false,
})
