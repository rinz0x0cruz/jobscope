import { createRootRoute, createRoute, createRouter, createHashHistory } from '@tanstack/react-router'
import App from './App'
import { searchSchema } from './lib/urlState'

// Root validates the URL search params (hash-based so it works from file:// and the
// GitHub Pages subpath). The whole dashboard is one route; "tabs" and filters are
// just search-param state, which keeps every view shareable and back/forward-able.
const rootRoute = createRootRoute({
  validateSearch: (search: Record<string, unknown>) => searchSchema.parse(search),
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
