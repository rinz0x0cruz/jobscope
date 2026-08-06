import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { CaptureDialog } from '@/features/capture/CaptureDialog'
import type { CaptureDialogProps } from '@/features/capture/CaptureDialog'
import { CaptureError, captureRole } from '@/lib/capture'
import type { CaptureResult } from '@/lib/capture'

// Only the network call is stubbed. CaptureError stays real, because the dialog
// branches on `instanceof` and a fake class would pass a test the app fails.
vi.mock('@/lib/capture', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/capture')>()),
  captureRole: vi.fn(),
}))

const DESCRIPTION = 'Security Analyst\nCompany: Acme Security\nLocation: Bengaluru, India'

function parsed(over: Partial<CaptureResult> = {}): CaptureResult {
  return {
    ok: true,
    job_id: 'job:acme:analyst',
    title: 'Security Analyst',
    company: 'Acme Security',
    location: 'Bengaluru, India',
    url: 'https://boards.greenhouse.io/acme/jobs/1234',
    source: 'text',
    score: 72,
    tier: 'Strong',
    rationale: 'SIEM and incident response',
    duplicate_of: '',
    warnings: [],
    saved: false,
    ...over,
  }
}

function renderDialog(over: Partial<CaptureDialogProps> = {}) {
  const onOpenChange = vi.fn()
  const onSaved = vi.fn()
  render(<CaptureDialog open onOpenChange={onOpenChange} onSaved={onSaved} {...over} />)
  return { onOpenChange, onSaved }
}

const previewButton = () => screen.getByRole('button', { name: /^preview$/i })
const saveButton = () => screen.getByRole('button', { name: /save to review/i })
const description = () => screen.getByPlaceholderText(/what you will do/i)
const postingUrl = () => screen.getByPlaceholderText(/boards\.greenhouse\.io/i)

describe('CaptureDialog', () => {
  beforeEach(() => {
    vi.mocked(captureRole).mockReset()
  })

  it('previews a pasted description without saving it', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())

    // scoped to the parse panel: the pasted description repeats these same words
    const panel = (await screen.findByText('Security Analyst')).parentElement!
    expect(captureRole).toHaveBeenCalledWith({ url: '', text: DESCRIPTION, save: false })
    expect(within(panel).getByText(/Acme Security/)).toBeInTheDocument()
    expect(within(panel).getByText(/Bengaluru, India/)).toBeInTheDocument()
    expect(within(panel).getByText('72')).toBeInTheDocument()
    expect(within(panel).getByText(/Strong/)).toBeInTheDocument()
  })

  it('sends the posting URL when that is what was filled in', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed({ source: 'url' }))
    renderDialog()

    fireEvent.change(postingUrl(), { target: { value: '  https://boards.greenhouse.io/acme/jobs/1234  ' } })
    fireEvent.click(previewButton())

    await waitFor(() => expect(captureRole).toHaveBeenCalledWith({
      url: 'https://boards.greenhouse.io/acme/jobs/1234',
      text: '',
      save: false,
    }))
  })

  it('refuses to save anything the user has not seen parsed first', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    renderDialog()

    // nothing typed: there is nothing to preview and nothing to save
    expect(previewButton()).toBeDisabled()
    expect(saveButton()).toBeDisabled()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    expect(previewButton()).toBeEnabled()
    expect(saveButton()).toBeDisabled()

    fireEvent.click(previewButton())
    await screen.findByText('Security Analyst')
    expect(saveButton()).toBeEnabled()
  })

  it('confirms the capture, reports it upward and closes', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    const { onOpenChange, onSaved } = renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())
    await screen.findByText('Security Analyst')

    vi.mocked(captureRole).mockResolvedValue(parsed({ saved: true, is_new: true }))
    fireEvent.click(saveButton())

    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(captureRole).toHaveBeenLastCalledWith({ url: '', text: DESCRIPTION, save: true })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('blocks both actions while a request is in flight', async () => {
    let release: (value: CaptureResult) => void = () => {}
    vi.mocked(captureRole).mockReturnValue(new Promise<CaptureResult>((resolve) => {
      release = resolve
    }))
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())

    await waitFor(() => expect(previewButton()).toBeDisabled())
    expect(saveButton()).toBeDisabled()

    release(parsed())
    await screen.findByText('Security Analyst')
    expect(previewButton()).toBeEnabled()
  })

  it('surfaces a failure as an alert instead of a silent no-op', async () => {
    vi.mocked(captureRole).mockRejectedValue(new Error('capture failed (500)'))
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('capture failed (500)')
    expect(previewButton()).toBeEnabled()
  })

  it('drops a stale parse when the next URL turns out to be auth-walled', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())
    await screen.findByText('Security Analyst')

    vi.mocked(captureRole).mockRejectedValue(
      new CaptureError('paste the description instead', true),
    )
    fireEvent.change(postingUrl(), { target: { value: 'https://www.linkedin.com/jobs/view/1' } })
    fireEvent.click(previewButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('paste the description instead')
    // the old parse belonged to different input, so it must not stay on screen
    await waitFor(() => expect(screen.queryByText('Security Analyst')).not.toBeInTheDocument())
    expect(saveButton()).toBeDisabled()
  })

  it('warns before saving a duplicate or a filtered-out role', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed({
      tier: 'Skip',
      duplicate_of: 'job:acme:analyst',
      warnings: ['No resume imported, so the score is provisional.'],
    }))
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())

    expect(await screen.findByText(/will not enter the review queue/i)).toBeInTheDocument()
    expect(screen.getByText(/updates the existing role instead of adding a copy/i)).toBeInTheDocument()
    expect(screen.getByText(/No resume imported/i)).toBeInTheDocument()
    // still saveable: the warnings inform the decision rather than block it
    expect(saveButton()).toBeEnabled()
  })

  it('explains that capture needs the local control plane running', async () => {
    vi.mocked(captureRole).mockResolvedValue(null)
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(/jobscope serve/i)
  })

  it('opens with focus inside the dialog and closes on Escape', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    const { onOpenChange } = renderDialog()

    const dialog = screen.getByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))

    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('forgets the previous attempt when dismissed', async () => {
    vi.mocked(captureRole).mockResolvedValue(parsed())
    renderDialog()

    fireEvent.change(description(), { target: { value: DESCRIPTION } })
    fireEvent.click(previewButton())
    await screen.findByText('Security Analyst')

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => expect(description()).toHaveValue(''))
    expect(postingUrl()).toHaveValue('')
    expect(screen.queryByText('Security Analyst')).not.toBeInTheDocument()
  })
})
