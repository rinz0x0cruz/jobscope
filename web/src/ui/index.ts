// v2 design-system primitives (P0). Token-driven, flat, dependency-free.

export { Button } from './Button'
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button'

export { IconButton } from './IconButton'
export type { IconButtonProps, IconButtonSize } from './IconButton'

export { Card } from './Card'
export type { CardProps } from './Card'

export { StatCard } from './StatCard'
export type { StatCardProps, StatCardDelta } from './StatCard'

export { Segmented } from './Segmented'
export type { SegmentedProps, SegmentedOption } from './Segmented'

export { Chip } from './Chip'
export type { ChipProps } from './Chip'

export { Input } from './Input'
export type { InputProps } from './Input'

export { Badge } from './Badge'
export type { BadgeProps, BadgeTone } from './Badge'

export { animate, prefersReducedMotion, viewTransition } from './motion'
