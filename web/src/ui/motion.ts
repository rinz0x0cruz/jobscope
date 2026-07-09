/**
 * Dependency-free native motion layer for the v2 UI (replaces `motion` and
 * `lottie-react`). Everything here honors `prefers-reduced-motion` and is
 * safe to call in non-DOM (SSR) environments.
 */

/**
 * Whether the user has requested reduced motion via the OS/browser.
 *
 * SSR-safe: returns `false` when `window` or `matchMedia` are unavailable.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Imperative Web Animations API helper with built-in guards.
 *
 * Returns `null` (and animates nothing) when the element is missing, the user
 * prefers reduced motion, or `Element.animate` is unavailable — in which case
 * the caller should have already applied the final state. Otherwise returns the
 * running {@link Animation}.
 */
export function animate(
  el: Element | null,
  keyframes: Keyframe[] | PropertyIndexedKeyframes,
  options?: number | KeyframeAnimationOptions,
): Animation | null {
  if (!el || prefersReducedMotion() || typeof el.animate !== 'function') {
    return null
  }
  return el.animate(keyframes, options)
}

/**
 * Run a DOM mutation inside a View Transition when supported and motion is
 * allowed; otherwise apply `update` synchronously. Always applies the update.
 */
export function viewTransition(update: () => void): void {
  const d = document as Document & {
    startViewTransition?: (callback: () => void) => unknown
  }
  if (typeof d.startViewTransition === 'function' && !prefersReducedMotion()) {
    d.startViewTransition(update)
    return
  }
  update()
}
