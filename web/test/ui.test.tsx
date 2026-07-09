import { describe, expect, it, vi } from 'vitest'
import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { Badge, Button, Card, Chip, IconButton, Input, Segmented, StatCard } from '@/ui'

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
