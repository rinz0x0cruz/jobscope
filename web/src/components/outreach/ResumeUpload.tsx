import { useRef, useState } from 'react'
import { Loader2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import type { Profile } from '@/lib/schema'
import { uploadResume } from '@/lib/outreach'

/**
 * Upload a résumé from the dashboard. Local `jobscope serve` only (the file is
 * stored on your machine under data/resumes/ and imported like `resume import`);
 * on the published site there's no backend, so this control isn't rendered. On
 * success the parent's profile updates live.
 */
export function ResumeUpload({ token, onUploaded }: { token: string; onUploaded: (p: Profile | null) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same filename
    if (!file) return
    setBusy(true)
    try {
      const res = await uploadResume(file, token)
      if (res.ok) {
        toast.success(`Imported ${res.resume || file.name}`)
        onUploaded(res.profile ?? null)
      } else {
        toast.error(res.error || 'Upload failed')
      }
    } catch {
      toast.error('Could not reach jobscope serve.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".md,.markdown,.txt,.json,.pdf"
        onChange={onFile}
        className="hidden"
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-bg2 px-3 py-1.5 text-[13px] font-medium text-fg transition hover:border-border-h disabled:opacity-50"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Upload résumé
      </button>
      <span className="text-[11px] text-mute">.md, .txt, .json, or .pdf — stored locally, imports on the spot</span>
    </div>
  )
}
