import { createContext } from 'react'

export type ScoreFormat = 'number' | 'grade'

export interface ScoreFormatContextValue {
  format: ScoreFormat
  setFormat: (format: ScoreFormat) => void
  toggle: () => void
}

export const ScoreFormatContext = createContext<ScoreFormatContextValue>({
  format: 'number',
  setFormat: () => {},
  toggle: () => {},
})