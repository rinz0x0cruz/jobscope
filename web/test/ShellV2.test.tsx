import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render } from '@testing-library/react'
import { ShellV2 } from '@/app/ShellV2'
import { searchSchema } from '@/lib/urlState'
import { dashboard, jobRow } from './factories'

describe('ShellV2', () => {
  it('closes the current reader with Escape', () => {
    const job = jobRow({ id: 'selected', title: 'Security Engineer' })
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard({ rows: [job] })}
        state={searchSchema.parse({ view: 'review', job: job.id })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onStateChange).toHaveBeenCalledWith({ job: undefined }, { replace: true })
  })

  it('clears the reader when switching primary views', () => {
    const job = jobRow({ id: 'selected', title: 'Security Engineer' })
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard({ rows: [job] })}
        state={searchSchema.parse({ view: 'review', job: job.id })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: '3' })
    expect(onStateChange).toHaveBeenCalledWith({ view: 'pipeline', job: undefined })
  })

  it('maps shortcut six to Settings', () => {
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard()}
        state={searchSchema.parse({ view: 'review' })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )
    fireEvent.keyDown(window, { key: '6' })
    expect(onStateChange).toHaveBeenCalledWith({ view: 'settings', job: undefined, company: undefined })
  })
})
