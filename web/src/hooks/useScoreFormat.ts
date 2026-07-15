import { useContext } from 'react'
import { ScoreFormatContext, type ScoreFormatContextValue } from './scoreFormatContext'

export type { ScoreFormat } from './scoreFormatContext'

export function useScoreFormat(): ScoreFormatContextValue {
  return useContext(ScoreFormatContext)
}