import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './router'
import { ScoreFormatProvider } from './hooks/ScoreFormatProvider'
import '@fontsource/manrope/latin-400.css'
import '@fontsource/manrope/latin-500.css'
import '@fontsource/manrope/latin-600.css'
import '@fontsource/manrope/latin-700.css'
import '@fontsource/source-serif-4/latin-400.css'
import '@fontsource/source-serif-4/latin-600.css'
import './styles/theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ScoreFormatProvider>
      <RouterProvider router={router} />
    </ScoreFormatProvider>
  </StrictMode>,
)
