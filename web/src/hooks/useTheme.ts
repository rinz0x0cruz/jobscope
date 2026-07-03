import { useCallback, useEffect, useState } from 'react'

type Theme = 'dark' | 'light'
const KEY = 'jobscope-theme'

function readInitial(): Theme {
  if (typeof document === 'undefined') return 'dark'
  return document.documentElement.classList.contains('light') ? 'light' : 'dark'
}

/** Class-based light/dark theme, persisted to localStorage. The initial class
 *  is applied by the inline script in index.html to avoid a flash (FOUC). */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readInitial)

  useEffect(() => {
    const el = document.documentElement
    el.classList.remove('dark', 'light')
    el.classList.add(theme)
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* localStorage unavailable (private mode / file://) — ignore */
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return { theme, toggle }
}
