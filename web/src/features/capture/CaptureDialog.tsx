// Capture role: paste a public posting URL or the description itself, see exactly
// what was parsed, then confirm. Nothing is stored until Save is pressed.

import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Loader2 } from 'lucide-react'
import { CaptureError, captureRole, type CaptureResult } from '@/lib/capture'

export interface CaptureDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved?: () => void
}

const FIELD =
  'w-full rounded-md border border-line bg-inset px-3 py-2 text-[13px] text-ink ' +
  'outline-none placeholder:text-ink-3 focus-visible:border-brand'

export function CaptureDialog({ open, onOpenChange, onSaved }: CaptureDialogProps) {
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<CaptureResult | null>(null)

  const reset = () => {
    setUrl('')
    setText('')
    setError('')
    setPreview(null)
  }

  const close = (next: boolean) => {
    onOpenChange(next)
    if (!next) reset()
  }

  const run = async (save: boolean) => {
    setBusy(true)
    setError('')
    try {
      const result = await captureRole({ url: url.trim(), text: text.trim(), save })
      if (!result) {
        setError('Capture needs the local control plane. Start `jobscope serve` and retry.')
        return
      }
      setPreview(result)
      if (save) {
        onSaved?.()
        close(false)
      }
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'capture failed')
      if (exception instanceof CaptureError && exception.needsText) setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={close}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-[10%] z-50 max-h-[80vh] w-[92vw] max-w-xl -translate-x-1/2 overflow-y-auto rounded-card border border-line bg-panel p-5 shadow-[var(--shadow-panel)] outline-none"
        >
          <Dialog.Title className="text-[15px] font-semibold text-ink">Capture role</Dialog.Title>
          <Dialog.Description className="mt-1 text-[12px] text-ink-3">
            Paste a public job board URL or the description itself. Nothing is saved until you confirm.
          </Dialog.Description>

          <div className="mt-4 grid gap-3">
            <label className="grid gap-1.5">
              <span className="text-[10px] font-semibold uppercase text-ink-3">Posting URL</span>
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://boards.greenhouse.io/acme/jobs/1234"
                className={FIELD}
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[10px] font-semibold uppercase text-ink-3">
                Or paste the description
              </span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={7}
                placeholder={'Security Analyst\nCompany: Acme\nLocation: Bengaluru, India\n\nWhat you will do…'}
                className={`${FIELD} resize-y font-mono text-[12px] leading-5`}
              />
            </label>
          </div>

          {error && (
            <p className="mt-3 text-[12px]" style={{ color: 'var(--danger)' }} role="alert">
              {error}
            </p>
          )}

          {preview && !preview.saved && (
            <div className="mt-4 rounded-md border border-line bg-inset p-3">
              <p className="text-[13px] font-semibold text-ink">{preview.title || '(no title found)'}</p>
              <p className="mt-0.5 text-[12px] text-ink-2">
                {preview.company || '(no company found)'}
                {preview.location ? ` · ${preview.location}` : ''}
              </p>
              {preview.tier && (
                <p className="mt-1.5 text-[12px] text-ink-2">
                  Scored <span className="font-mono text-ink">{preview.score}</span> · {preview.tier}
                </p>
              )}
              {preview.tier === 'Skip' && (
                <p className="mt-1.5 text-[12px]" style={{ color: 'var(--warning)' }}>
                  Filtered to Skip, so saving stores it but it will not enter the review queue.
                </p>
              )}
              {preview.duplicate_of && (
                <p className="mt-1.5 text-[12px]" style={{ color: 'var(--warning)' }}>
                  Already captured — saving updates the existing role instead of adding a copy.
                </p>
              )}
              {preview.warnings.map((warning) => (
                <p key={warning} className="mt-1.5 text-[12px]" style={{ color: 'var(--warning)' }}>
                  {warning}
                </p>
              ))}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
            <Dialog.Close className="h-9 rounded-md border border-line px-3 text-[12px] font-medium text-ink-2 hover:border-line-strong hover:text-ink">
              Cancel
            </Dialog.Close>
            <button
              type="button"
              onClick={() => void run(false)}
              disabled={busy || (!url.trim() && !text.trim())}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-brand px-3 text-[12px] font-semibold text-brand disabled:opacity-50"
            >
              {busy && !preview ? <Loader2 size={14} className="animate-spin" /> : null}
              Preview
            </button>
            <button
              type="button"
              onClick={() => void run(true)}
              disabled={busy || !preview}
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-4 text-[12px] font-semibold text-on-brand disabled:opacity-50"
            >
              {busy && preview ? <Loader2 size={14} className="animate-spin" /> : null}
              Save to review
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
