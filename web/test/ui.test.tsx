import { describe, expect, it, vi } from 'vitest'
import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { Badge, Button, Card, Chip, IconButton, Input, Segmented, StatCard, WorkspaceHeader, viewTransition } from '@/ui'

describe('viewTransition', () => {
  it('handles an interrupted transition without an unobserved rejection', () => {
    const observeAbort = vi.fn()
    const start = vi.fn((update: () => void) => {
      update()
      return { ready: { catch: observeAbort } }
    })
    const original = Object.getOwnPropertyDescriptor(document, 'startViewTransition')
    Object.defineProperty(document, 'startViewTransition', { configurable: true, value: start })
    const update = vi.fn()

    try {
      viewTransition(update)
      expect(update).toHaveBeenCalledOnce()
      expect(observeAbort).toHaveBeenCalledOnce()
      expect(observeAbort).toHaveBeenCalledWith(expect.any(Function))
    } finally {
      if (original) Object.defineProperty(document, 'startViewTransition', original)
      else Reflect.deleteProperty(document, 'startViewTransition')
    }
  })

  it('applies the update when the native transition cannot start', () => {
    const original = Object.getOwnPropertyDescriptor(document, 'startViewTransition')
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: vi.fn(() => { throw new DOMException('not ready', 'InvalidStateError') }),
    })
    const update = vi.fn()

    try {
      expect(() => viewTransition(update)).not.toThrow()
      expect(update).toHaveBeenCalledOnce()
    } finally {
      if (original) Object.defineProperty(document, 'startViewTransition', original)
      else Reflect.deleteProperty(document, 'startViewTransition')
    }
  })
})

describe('Button', () => {
  it('renders its label and fires onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Save</Button>)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('reflects the disabled prop', () => {
    render(
      <Button variant="secondary" size="sm" disabled>
        Nope
      </Button>,
    )
    expect(screen.getByRole('button', { name: 'Nope' })).toBeDisabled()
  })
})

describe('WorkspaceHeader', () => {
  it('owns the route title and keeps actions beside its context', () => {
    render(
      <WorkspaceHeader
        eyebrow="Progress"
        title="Analytics"
        description="Measured outcomes"
        actions={<button>Applications</button>}
        accent="signal"
      />,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument()
    expect(screen.getByText('Progress')).toHaveClass('text-signal')
    expect(screen.getByRole('button', { name: 'Applications' })).toBeInTheDocument()
  })
})

describe('IconButton', () => {
  it('exposes its label as the accessible name', () => {
    render(
      <IconButton label="Refresh">
        <span aria-hidden="true">i</span>
      </IconButton>,
    )
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })
})

describe('Card', () => {
  it('renders the title, actions, and children', () => {
    render(
      <Card title="Overview" actions={<button>Edit</button>}>
        <p>Body content</p>
      </Card>,
    )
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByText('Body content')).toBeInTheDocument()
  })
})

describe('StatCard', () => {
  it('renders the label, value, and a positive delta', () => {
    render(<StatCard label="Applications" value={42} delta={{ value: '+8', positive: true }} />)
    expect(screen.getByText('Applications')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('+8')).toBeInTheDocument()
  })
})

describe('Segmented', () => {
  const options = [
    { value: 'all', label: 'All', count: 12 },
    { value: 'strong', label: 'Strong', count: 3 },
  ]

  it('renders a radiogroup and marks the active radio', () => {
    render(<Segmented ariaLabel="Filter by tier" options={options} value="strong" onChange={() => {}} />)
    expect(screen.getByRole('radiogroup', { name: 'Filter by tier' })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(2)
    expect(screen.getByRole('radio', { name: /Strong/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /All/ })).toHaveAttribute('aria-checked', 'false')
  })

  it('fires onChange with the chosen value', () => {
    const onChange = vi.fn()
    render(<Segmented ariaLabel="Filter by tier" options={options} value="strong" onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: /All/ }))
    expect(onChange).toHaveBeenCalledWith('all')
  })
})

describe('Chip', () => {
  it('renders children and a remove button that fires onRemove', () => {
    const onRemove = vi.fn()
    render(<Chip onRemove={onRemove}>Python</Chip>)
    expect(screen.getByText('Python')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  it('omits the remove button when onRemove is absent', () => {
    render(<Chip>Static</Chip>)
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
  })
})

describe('Badge', () => {
  it('renders its content', () => {
    render(<Badge tone="brand">New</Badge>)
    expect(screen.getByText('New')).toBeInTheDocument()
  })
})

describe('Input', () => {
  it('forwards its ref to the underlying input element', () => {
    const ref = createRef<HTMLInputElement>()
    render(<Input ref={ref} placeholder="Search jobs" />)
    expect(ref.current).toBeInstanceOf(HTMLInputElement)
    expect(screen.getByPlaceholderText('Search jobs')).toBe(ref.current)
  })
})
