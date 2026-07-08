import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './router'
import { ScoreFormatProvider } from './hooks/useScoreFormat'
import './styles/theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ScoreFormatProvider>
      <RouterProvider router={router} />
    </ScoreFormatProvider>
  </StrictMode>,
)
