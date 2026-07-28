import { useEffect, useEffectEvent, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Clock3,
  Loader2,
  MailSearch,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  SkipForward,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Segmented, WorkspaceHeader, animate, viewTransition } from '@/ui'
import {
  campaignAction,
  createCampaign,
  getCampaign,
  listCampaigns,
  type Campaign,
  type CampaignActionResult,
  type CampaignContact,
  type CampaignDetailResult,
  type CampaignHistoryItem,
  type CampaignSummary,
  type OutreachSnapshot,
  type OutreachPolicy,
  type CampaignSnapshotTarget,
  type CampaignTarget,
} from '@/lib/campaigns'

export interface CampaignsViewProps {
  token: string
  selectedId?: string
  onSelect: (campaignId?: string) => void
  onOpenApplications: () => void
}

function privateWorkspaceOrigin(): string {
  const fallback = 'http://127.0.0.1:8799'
  try {
    const value = new URL(import.meta.env.VITE_JOBSCOPE_PRIVATE_ORIGIN || fallback)
    const loopback = ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(value.hostname.toLowerCase())
    if ((!loopback && value.protocol !== 'https:') || value.username || value.password) return fallback
    if ((value.pathname && value.pathname !== '/') || value.search || value.hash) return fallback
    return value.origin
  } catch {
    return fallback
  }
}

export function CampaignsView({ token, selectedId, onSelect, onOpenApplications }: CampaignsViewProps) {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([])
  const [detail, setDetail] = useState<CampaignDetailResult | null>(null)
  const [targetId, setTargetId] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [creatingFollowups, setCreatingFollowups] = useState(false)
  const [name, setName] = useState('India cybersecurity outreach')
  const [count, setCount] = useState(10)
  const [regionWeight, setRegionWeight] = useState(50)
  const [compensationWeight, setCompensationWeight] = useState(30)
  const [growthWeight, setGrowthWeight] = useState(20)
  const [composerMode, setComposerMode] = useState<'cold' | 'followup'>('cold')
  const listRef = useRef<HTMLUListElement | null>(null)
  const detailRef = useRef<HTMLDivElement | null>(null)
  const acceptCampaigns = useEffectEvent((values: CampaignSummary[]) => {
    setCampaigns(values)
    if (!selectedId && values[0]) onSelect(values[0].id)
    else if (selectedId && !values.some((campaign) => campaign.id === selectedId)) {
      onSelect(values[0]?.id)
    }
  })

  useEffect(() => {
    let live = true
    void listCampaigns(token)
      .then((values) => {
        if (!live) return
        acceptCampaigns(values)
      })
      .catch((error) => live && toast.error(error instanceof Error ? error.message : 'Could not load outreach'))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [token])

  useEffect(() => {
    if (!selectedId) return
    let live = true
    void getCampaign(token, selectedId)
      .then((value) => {
        if (!live) return
        setDetail(value)
        setTargetId((current) => value.targets.some((target) => target.id === current)
          ? current
          : value.targets[0]?.id ?? '')
      })
      .catch((error) => live && toast.error(error instanceof Error ? error.message : 'Could not load campaign'))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [token, selectedId])

  useEffect(() => {
    const rows = listRef.current?.querySelectorAll('[data-outreach-row]') ?? []
    rows.forEach((row, index) => animate(row, [
      { opacity: 0, transform: 'translateX(-8px)' },
      { opacity: 1, transform: 'translateX(0)' },
    ], { duration: 220, delay: Math.min(index * 35, 280), easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards' }))
  }, [campaigns.length])

  async function reload(campaignId = selectedId) {
    const [values, nextDetail] = await Promise.all([
      listCampaigns(token),
      campaignId ? getCampaign(token, campaignId) : Promise.resolve(null),
    ])
    setCampaigns(values)
    setDetail(nextDetail)
  }

  async function acceptDeletedCampaign() {
    const values = await listCampaigns(token)
    setCampaigns(values)
    setDetail(null)
    setTargetId('')
    onSelect(values[0]?.id)
  }

  async function submitCreate(event: React.FormEvent) {
    event.preventDefault()
    const total = regionWeight + compensationWeight + growthWeight
    if (total !== 100) {
      toast.error('Ranking weights must total 100%')
      return
    }
    setCreating(true)
    try {
      const result = await createCampaign(token, {
        name: name.trim(),
        requested_count: count,
        weights: {
          region: regionWeight / 100,
          compensation: compensationWeight / 100,
          growth: growthWeight / 100,
        },
      })
      setDetail(result)
      setTargetId(result.targets[0]?.id ?? '')
      onSelect(result.campaign.id)
      setCampaigns(await listCampaigns(token))
      toast.success(`Ranked ${result.targets.length} unique companies`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not create campaign')
    } finally {
      setCreating(false)
    }
  }

  async function buildFollowups() {
    setCreatingFollowups(true)
    try {
      const result = await createCampaign(token, {
        name: 'Recruiter follow-ups', requested_count: count,
        purpose: 'followup', include_cold: true, include_applications: true,
      })
      setDetail(result)
      setTargetId(result.targets[0]?.id ?? '')
      onSelect(result.campaign.id)
      setCampaigns(await listCampaigns(token))
      toast.success(`Prepared ${result.targets.length} follow-up${result.targets.length === 1 ? '' : 's'} for review`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not build follow-up queue')
    } finally {
      setCreatingFollowups(false)
    }
  }

  const visibleDetail = selectedId && detail?.campaign.id === selectedId ? detail : null
  const visibleTarget = visibleDetail?.targets.find((target) => target.id === targetId)
    ?? visibleDetail?.targets[0]
    ?? null
  useEffect(() => {
    animate(detailRef.current, [
      { opacity: 0, transform: 'translateX(8px)' },
      { opacity: 1, transform: 'translateX(0)' },
    ], { duration: 240, easing: 'cubic-bezier(.2,0,0,1)' })
  }, [visibleDetail?.campaign.id])
  const approved = campaigns.reduce((sum, campaign) => sum + (campaign.counts.approved ?? 0), 0)
  const sent = campaigns.reduce((sum, campaign) => sum + campaign.delivered_count, 0)
  const replies = campaigns.reduce((sum, campaign) => sum + campaign.response_count, 0)

  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <WorkspaceHeader
        eyebrow={<span className="flex items-center gap-1.5"><ShieldCheck size={13} aria-hidden="true" /> Private control plane</span>}
        title="Outreach"
        description="Build deliberate recruiter conversations. Every message stays individually reviewed, recipient-locked, and paced."
        actions={(
          <div className="flex gap-5 border-l border-line pl-4 text-right">
            <Metric label="Batches" value={campaigns.length} />
            <Metric label="Approved" value={approved} />
            <Metric label="Sent" value={sent} />
            <Metric label="Replies" value={replies} />
          </div>
        )}
        accent="brand"
      />

      <div className="shrink-0 border-b border-line bg-inset/35 px-4 py-2.5 sm:px-7">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <Segmented
            ariaLabel="Outreach type"
            value={composerMode}
            onChange={(value) => viewTransition(() => setComposerMode(value as 'cold' | 'followup'))}
            options={[
              { value: 'cold', label: 'Cold batches' },
              { value: 'followup', label: 'Follow-ups' },
            ]}
          />
          <p className="flex items-center gap-1.5 text-[11px] text-ink-3">
            <Sparkles size={13} className="text-signal" aria-hidden="true" />
            {composerMode === 'cold' ? 'Rank new companies with auditable evidence.' : 'Collect due application and cold-thread follow-ups.'}
          </p>
        </div>
        {composerMode === 'cold' ? (
          <form
            onSubmit={submitCreate}
            className="grid gap-2 md:grid-cols-[minmax(12rem,1fr)_repeat(4,minmax(4.5rem,.45fr))] xl:grid-cols-[minmax(12rem,1fr)_5rem_repeat(3,5.5rem)_auto]"
          >
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-label="Campaign name"
              className="h-9 min-w-0 rounded-md border border-line bg-panel px-3 text-[13px] text-ink outline-none transition-colors focus:border-brand"
            />
            <NumberInput label="Companies" value={count} onChange={setCount} min={1} max={100} />
            <NumberInput label="India %" value={regionWeight} onChange={setRegionWeight} min={0} max={100} />
            <NumberInput label="Comp %" value={compensationWeight} onChange={setCompensationWeight} min={0} max={100} />
            <NumberInput label="Growth %" value={growthWeight} onChange={setGrowthWeight} min={0} max={100} />
            <button
              type="submit"
              disabled={creating || !name.trim() || count < 1}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand px-4 text-[12px] font-semibold text-white shadow-sm transition-colors hover:bg-brand-strong disabled:opacity-50 md:col-span-5 xl:col-span-1"
            >
              {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Create batch
            </button>
          </form>
        ) : (
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_7rem_auto] sm:items-end">
            <div>
              <p className="text-[12px] font-medium text-ink">Prepare one review queue from every due conversation.</p>
              <p className="mt-1 text-[11px] text-ink-3">No bulk approval and no send. Original recipients and thread identities remain locked.</p>
            </div>
            <NumberInput label="Maximum" value={count} onChange={setCount} min={1} max={100} />
            <button
              type="button"
              disabled={creatingFollowups || count < 1}
              onClick={() => void buildFollowups()}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-brand bg-panel px-4 text-[12px] font-semibold text-brand transition-transform hover:-translate-y-px disabled:translate-y-0 disabled:opacity-50"
            >
              {creatingFollowups ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Build follow-up queue
            </button>
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(250px,.48fr)_minmax(0,1.52fr)]">
        <div className={`${visibleDetail ? 'hidden lg:block' : 'block'} min-h-0 overflow-auto border-r border-line`}>
          {loading && campaigns.length === 0 ? (
            <Loading label="Loading outreach" />
          ) : campaigns.length ? (
            <ul ref={listRef}>
              {campaigns.map((campaign) => (
                <CampaignRow
                  key={campaign.id}
                  campaign={campaign}
                  selected={campaign.id === selectedId}
                  onSelect={() => onSelect(campaign.id)}
                />
              ))}
            </ul>
          ) : (
            <EmptyCampaigns />
          )}
        </div>
        <div ref={detailRef} className={`${visibleDetail ? 'block' : 'hidden lg:block'} min-h-0 overflow-auto`}>
          {visibleDetail ? (
            <CampaignDetail
              token={token}
              detail={visibleDetail}
              selectedTarget={visibleTarget}
              onTarget={setTargetId}
              onBack={() => onSelect(undefined)}
              onOpenApplications={onOpenApplications}
              onChanged={() => reload(visibleDetail.campaign.id)}
              onDeleted={acceptDeletedCampaign}
            />
          ) : (
            <NoCampaign />
          )}
        </div>
      </div>
    </section>
  )
}

function CampaignDetail({
  token,
  detail,
  selectedTarget,
  onTarget,
  onBack,
  onOpenApplications,
  onChanged,
  onDeleted,
}: {
  token: string
  detail: CampaignDetailResult
  selectedTarget: CampaignTarget | null
  onTarget: (targetId: string) => void
  onBack: () => void
  onOpenApplications: () => void
  onChanged: () => Promise<void>
  onDeleted: () => Promise<void>
}) {
  const [busy, setBusy] = useState('')
  const campaign = detail.campaign
  const followUp = Array.isArray(campaign.criteria.follow_up)
    ? campaign.criteria.follow_up.filter((item): item is { company: string } => (
      Boolean(item) && typeof item === 'object' && typeof (item as { company?: unknown }).company === 'string'
    ))
    : []
  const canDiscoverContacts = detail.targets.some((target) => (
    target.state === 'ranked'
    || target.state === 'needs_contact'
    || (target.state === 'failed' && target.error_code === 'contact_discovery_failed')
  ))

  async function discoverPending() {
    setBusy('discover_pending')
    try {
      const result = await checkedAction(token, {
        action: 'discover_pending', campaign_id: campaign.id, limit: 5, fetch: true,
      })
      await onChanged()
      toast.success(
        result.processed
          ? `Prepared ${result.drafted ?? 0} draft${result.drafted === 1 ? '' : 's'}; ${result.remaining ?? 0} ranked target${result.remaining === 1 ? '' : 's'} remain`
          : 'No ranked targets need contact discovery',
      )
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not discover recruiters')
    } finally {
      setBusy('')
    }
  }

  async function status(next: 'active' | 'paused' | 'cancelled') {
    setBusy(next)
    try {
      await checkedAction(token, { action: 'status', campaign_id: campaign.id, status: next })
      await onChanged()
      toast.success(next === 'active' ? 'Campaign active' : next === 'paused' ? 'Campaign paused' : 'Campaign cancelled')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not update campaign')
    } finally {
      setBusy('')
    }
  }

  async function deleteDraft() {
    if (!window.confirm(`Permanently delete the draft campaign “${campaign.name}”?`)) return
    setBusy('delete')
    try {
      await checkedAction(token, { action: 'delete', campaign_id: campaign.id })
      await onDeleted()
      toast.success('Draft campaign deleted')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete draft campaign')
    } finally {
      setBusy('')
    }
  }

  async function sendNext() {
    setBusy('send_next')
    try {
      const result = await campaignAction(token, { action: 'check_replies', fetch: true })
      if (!result.ok) throw new Error(result.error || 'Inbox reply check failed')
      await onChanged()
      const due = detail.counts.approved ?? 0
      toast.success(`${result.replied ?? 0} replies · ${result.opted_out ?? 0} opt-outs · ${due} approved due/review item${due === 1 ? '' : 's'}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not check replies and due work')
    } finally {
      setBusy('')
    }
  }

  async function checkReplies() {
    setBusy('check_replies')
    try {
      const result = await campaignAction(token, { action: 'check_replies', fetch: true })
      if (!result.ok) throw new Error(result.error || 'Inbox reply check failed')
      await onChanged()
      toast.success(
        `${result.replied ?? 0} new repl${result.replied === 1 ? 'y' : 'ies'} · ${result.opted_out ?? 0} opt-out${result.opted_out === 1 ? '' : 's'}`,
      )
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not check replies')
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <header className="border-b border-line px-5 py-5 sm:px-7">
        <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 text-[12px] text-ink-3 lg:hidden">
          <ArrowLeft size={14} /> Outreach
        </button>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xl font-semibold text-ink">{campaign.name}</h3>
              <StateBadge state={campaign.status} />
            </div>
            <p className="mt-1 text-[12px] text-ink-3">
              {campaign.requested_count} companies · {campaign.daily_limit}/day · {campaign.min_spacing_hours}h spacing · {campaign.send_window_start}–{campaign.send_window_end} {campaign.timezone}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton label="Check replies" onClick={checkReplies} busy={busy === 'check_replies'} Icon={RefreshCw} />
            {canDiscoverContacts && (
              <ActionButton label="Find recruiters" onClick={discoverPending} busy={busy === 'discover_pending'} Icon={MailSearch} />
            )}
            {campaign.status === 'active' ? (
              <ActionButton label="Pause" onClick={() => status('paused')} busy={busy === 'paused'} Icon={Pause} />
            ) : campaign.status !== 'cancelled' && campaign.status !== 'completed' ? (
              <ActionButton label={campaign.status === 'paused' ? 'Resume' : 'Start'} onClick={() => status('active')} busy={busy === 'active'} Icon={Play} primary />
            ) : null}
            {campaign.status === 'active' && (
              <ActionButton label="Check replies and due work" onClick={sendNext} busy={busy === 'send_next'} Icon={RefreshCw} />
            )}
            {campaign.status === 'draft' && (
              <ActionButton label="Delete draft" onClick={deleteDraft} busy={busy === 'delete'} Icon={Trash2} danger />
            )}
          </div>
        </div>
      </header>

      {followUp.length > 0 && (
        <section className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-[color-mix(in_srgb,var(--strong)_7%,transparent)] px-5 py-3 sm:px-7">
          <div>
            <p className="text-[10px] font-semibold uppercase text-strong">Routed to follow-up</p>
            <p className="mt-0.5 text-[12px] text-ink-2">
              {followUp.length} applied compan{followUp.length === 1 ? 'y was' : 'ies were'} excluded from cold outreach: {followUp.slice(0, 3).map((item) => item.company).join(', ')}{followUp.length > 3 ? ` +${followUp.length - 3}` : ''}
            </p>
          </div>
          <ActionButton label="Open applications" onClick={onOpenApplications} busy={false} Icon={ArrowRight} />
        </section>
      )}

      <div className="overflow-x-auto border-b border-line">
        <table className={`w-full border-collapse text-left ${campaign.purpose === 'followup' ? 'min-w-[680px]' : 'min-w-[760px]'}`}>
          <thead className="bg-inset text-[9px] font-semibold uppercase text-ink-3">
            <tr>
              <th className="w-16 px-4 py-2">{campaign.purpose === 'followup' ? 'Age' : 'Rank'}</th>
              <th className="px-3 py-2">Company</th>
              <th className="w-40 px-3 py-2">{campaign.purpose === 'followup' ? 'Source' : 'India / comp / growth'}</th>
              <th className="w-44 px-3 py-2">{campaign.purpose === 'followup' ? 'Recipient' : 'Contact'}</th>
              <th className="w-28 px-3 py-2">State</th>
            </tr>
          </thead>
          <tbody>
            {detail.targets.map((target) => (
              <TargetRow
                key={target.id}
                target={target}
                followup={campaign.purpose === 'followup'}
                selected={target.id === selectedTarget?.id}
                onSelect={() => onTarget(target.id)}
              />
            ))}
          </tbody>
        </table>
      </div>

      <DeliveryHistory
        items={detail.history}
        lastCheckedAt={detail.reply_tracking.last_checked_at}
        lastStatus={detail.reply_tracking.last_status}
      />

      {selectedTarget ? (
        <TargetEditor
          key={`${selectedTarget.id}:${selectedTarget.updated_at}`}
          token={token}
          campaign={campaign}
          target={selectedTarget}
          onChanged={onChanged}
        />
      ) : (
        <p className="px-5 py-10 text-center text-[13px] text-ink-3">No ranked targets in this campaign.</p>
      )}
    </div>
  )
}

function DeliveryHistory({ items, lastCheckedAt, lastStatus }: { items: CampaignHistoryItem[]; lastCheckedAt: string; lastStatus: string }) {
  if (!items.length) return null
  return (
    <section className="border-b border-line" aria-label="Sent email and reply history">
      <header className="flex flex-wrap items-center justify-between gap-2 bg-inset px-5 py-2 sm:px-7">
        <h4 className="text-[10px] font-semibold uppercase text-ink-3">Delivery history</h4>
        <span className="text-[10px] text-ink-3">
          {lastCheckedAt ? `Replies checked ${formatDate(lastCheckedAt)}` : 'Replies not checked yet'}
          {lastStatus ? ` · ${lastStatus.replaceAll('_', ' ')}` : ''}
        </span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <thead className="text-[9px] font-semibold uppercase text-ink-3">
            <tr>
              <th className="px-5 py-2 sm:px-7">Company</th>
              <th className="px-3 py-2">Sent</th>
              <th className="px-3 py-2">Recipient</th>
              <th className="px-3 py-2">Reply</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.target_id} className="border-t border-line text-[11px]">
                <td className="px-5 py-3 font-semibold text-ink sm:px-7">{item.company}</td>
                <td className="px-3 py-3 text-ink-3">{item.sent_at ? formatDate(item.sent_at) : 'Send outcome pending'}</td>
                <td className="max-w-52 truncate px-3 py-3 text-ink-2" title={item.recipient}>{item.recipient}</td>
                <td className="px-3 py-3">
                  {item.replied_at ? (
                    <span className="text-strong">
                      {item.state === 'opted_out' ? 'Opted out' : 'Replied'} {formatDate(item.replied_at)}
                      {item.reply_from ? ` · ${item.reply_from}` : ''}
                      {item.reply_subject ? ` · ${item.reply_subject}` : ''}
                    </span>
                  ) : (
                    <span className="text-ink-3">Awaiting reply</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function TargetEditor({
  token,
  campaign,
  target,
  onChanged,
}: {
  token: string
  campaign: Campaign
  target: CampaignTarget
  onChanged: () => Promise<void>
}) {
  const [email, setEmail] = useState(target.selected_email || target.contacts[0]?.email || '')
  const [subject, setSubject] = useState(target.subject)
  const [body, setBody] = useState(target.body)
  const [senderJurisdiction, setSenderJurisdiction] = useState(target.policy?.sender_jurisdiction || '')
  const [recipientJurisdiction, setRecipientJurisdiction] = useState(target.policy?.recipient_jurisdiction || '')
  const [recipientKind, setRecipientKind] = useState<OutreachPolicy['recipient_kind'] | ''>(target.policy?.recipient_kind || '')
  const [provenanceAt, setProvenanceAt] = useState(target.policy?.contact_provenance_at || '')
  const [basis, setBasis] = useState<OutreachPolicy['basis'] | ''>(target.policy?.basis || '')
  const [consent, setConsent] = useState<OutreachPolicy['consent'] | ''>(target.policy?.consent || '')
  const [optOutMethod, setOptOutMethod] = useState<OutreachPolicy['opt_out_method'] | ''>(target.policy?.opt_out_method || '')
  const [identityFooter, setIdentityFooter] = useState(target.policy?.identity_footer === true)
  const [reviewer, setReviewer] = useState(target.policy?.reviewer || '')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState('')
  const deliveryUnknown = target.error_code === 'delivery_unknown'
  const editable = !deliveryUnknown && !['sent', 'replied', 'skipped', 'opted_out'].includes(target.state)
  const hasDraft = Boolean(target.subject || target.body || target.state === 'draft' || target.state === 'approved')

  async function discover() {
    setBusy('discover')
    try {
      const result = await checkedAction(token, { action: 'discover', target_id: target.id, force: true, fetch: true })
      await onChanged()
      toast.success(result.target?.selected_email ? 'Recruiter selected and draft created' : 'Contact lookup complete')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not find recruiter')
    } finally {
      setBusy('')
    }
  }

  async function saveDraft() {
    const payload: Record<string, unknown> & { action: string } = {
      action: 'draft', target_id: target.id, selected_email: email,
    }
    if (hasDraft) {
      payload.subject = subject
      payload.body = body
    }
    const result = await checkedAction(token, payload)
    if (result.target) {
      setSubject(result.target.subject)
      setBody(result.target.body)
    }
    return result
  }

  async function saveOnly() {
    setBusy('save')
    try {
      await saveDraft()
      await onChanged()
      toast.success('Draft saved; approval reset')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save draft')
    } finally {
      setBusy('')
    }
  }

  async function approve() {
    setBusy('approve')
    try {
      const saved = await saveDraft()
      if (!senderJurisdiction || !recipientJurisdiction || !recipientKind || !provenanceAt
          || !basis || !consent || !optOutMethod || !identityFooter || !reviewer) {
        throw new Error('Complete the compliance review before approval')
      }
      const policy: OutreachPolicy = {
        sender_jurisdiction: senderJurisdiction,
        recipient_jurisdiction: recipientJurisdiction,
        recipient_kind: recipientKind,
        contact_source: saved.target?.selected_source || target.selected_source,
        contact_provenance_at: provenanceAt,
        purpose: campaign.purpose || 'cold',
        basis,
        consent,
        identity_footer: identityFooter,
        opt_out_method: optOutMethod,
        reviewer,
        policy_version: 'outreach-policy-v1',
      }
      await checkedAction(token, { action: 'approve', target_id: target.id, policy })
      await onChanged()
      toast.success('Email approved and scheduled')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not approve email')
    } finally {
      setBusy('')
    }
  }

  async function sendNow() {
    setBusy('send_now')
    try {
      const result = await campaignAction(token, { action: 'send_now', target_id: target.id })
      if (!result.ok) throw new Error(messageForCode(result.code))
      await onChanged()
      toast.success('Approved email sent')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not send email')
    } finally {
      setBusy('')
    }
  }

  async function skip() {
    setBusy('skip')
    try {
      await checkedAction(token, { action: 'skip', target_id: target.id })
      await onChanged()
      toast.success(`${target.company} skipped`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not skip target')
    } finally {
      setBusy('')
    }
  }

  async function resolveUnknown(outcome: 'sent' | 'not_sent') {
    setBusy(`resolve_${outcome}`)
    try {
      await checkedAction(token, {
        action: 'resolve_delivery', target_id: target.id, outcome,
      })
      await onChanged()
      toast.success(outcome === 'sent'
        ? 'Delivery marked sent after manual verification'
        : 'Returned to draft; review and approve before retrying')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not resolve delivery')
    } finally {
      setBusy('')
    }
  }

  async function reconcileUnknown() {
    setBusy('reconcile_sent')
    try {
      const result = await campaignAction(token, {
        action: 'reconcile_delivery', target_id: target.id,
      })
      if (!result.ok) throw new Error(messageForCode(result.code))
      await onChanged()
      toast.success(result.status === 'sent'
        ? 'Exact Message-ID found once in Sent; delivery marked sent'
        : 'Message-ID not found in Sent; returned to draft for review')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not check Sent mail')
    } finally {
      setBusy('')
    }
  }

  async function resolveFeedback(outcome: 'delivered' | 'hard_bounce') {
    setBusy(`feedback_${outcome}`)
    try {
      await checkedAction(token, {
        action: 'resolve_feedback', target_id: target.id, outcome,
      })
      await onChanged()
      toast.success(outcome === 'delivered'
        ? 'Transient bounce cleared after delivery verification'
        : 'Hard bounce confirmed; recipient suppressed')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not resolve provider feedback')
    } finally {
      setBusy('')
    }
  }

  return (
    <section aria-label={`Review ${target.company}`}>
      <header className="border-b border-line bg-inset/35 px-5 py-4 sm:px-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase text-ink-3">Individual review</p>
            <h4 className="mt-1 text-[16px] font-semibold text-ink">{target.company}</h4>
            <p className="mt-1 text-[11px] text-ink-3">
              {campaign.purpose === 'followup'
                ? `${Math.round(target.rank_score)} days since last action`
                : `Score ${target.rank_score.toFixed(1)} · ${(target.evidence_coverage * 100).toFixed(0)}% evidence coverage`}
            </p>
          </div>
          <StateBadge state={targetDisplayState(target)} />
        </div>
      </header>

      {campaign.purpose === 'followup' ? (
        <div className="grid border-b border-line sm:grid-cols-3">
          <FollowupFact label="Source" value={target.source_target_id ? 'Prior cold email' : 'Application'} />
          <FollowupFact label="Due since" value={target.evidence.anchor ? formatDate(target.evidence.anchor) : 'Unknown'} />
          <FollowupFact label="Recipient" value={target.recipient_locked ? 'Locked to original' : 'Verified contact'} />
        </div>
      ) : (
        <div className="grid border-b border-line md:grid-cols-3">
          <Evidence label="India relevance" score={target.region_score} lines={target.evidence.region} />
          <Evidence label="Compensation" score={target.compensation_score} lines={target.evidence.compensation} />
          <Evidence label="Growth" score={target.growth_score} lines={target.evidence.growth} />
        </div>
      )}

      <div className="space-y-4 px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-[240px] flex-1 text-[10px] font-semibold uppercase text-ink-3">
            Recipient
            <select
              value={email}
              onChange={(event) => { setEmail(event.target.value); setDirty(true) }}
              disabled={!editable || target.contacts.length === 0 || target.recipient_locked}
              className="mt-1 h-9 w-full rounded-md border border-line bg-inset px-3 text-[13px] font-normal normal-case text-ink outline-none focus:border-line-strong"
            >
              {!email && <option value="">No verified recruiter selected</option>}
              {target.contacts.map((contact) => (
                <option key={contact.email} value={contact.email}>
                  {contact.email} · {contact.source}/{contact.confidence}{contact.source === 'role_inbox' ? ' · manual fallback' : ''}
                </option>
              ))}
            </select>
          </label>
          {editable && !target.recipient_locked && (
            <ActionButton label="Find recruiter" onClick={discover} busy={busy === 'discover'} Icon={MailSearch} />
          )}
        </div>

        {email && (
          <ContactNote contact={target.contacts.find((contact) => contact.email === email)} />
        )}
        {target.recipient_locked && (
          <p className="text-[11px] font-medium text-strong">Recipient locked to the original outreach address.</p>
        )}

        {target.resume_path && (
          <p className="text-[11px] text-ink-3">Attachment · <span className="font-medium text-ink-2">{fileName(target.resume_path)}</span></p>
        )}

        {hasDraft ? (
          <>
            <label className="block text-[10px] font-semibold uppercase text-ink-3">
              Subject
              <input
                value={subject}
                onChange={(event) => { setSubject(event.target.value); setDirty(true) }}
                readOnly={!editable}
                className="mt-1 h-9 w-full rounded-md border border-line bg-inset px-3 text-[13px] font-normal normal-case text-ink outline-none focus:border-line-strong read-only:text-ink-3"
              />
            </label>
            <label className="block text-[10px] font-semibold uppercase text-ink-3">
              Message
              <textarea
                value={body}
                onChange={(event) => { setBody(event.target.value); setDirty(true) }}
                readOnly={!editable}
                rows={9}
                className="mt-1 w-full resize-y rounded-md border border-line bg-inset px-3 py-2 text-[13px] font-normal leading-6 normal-case text-ink outline-none focus:border-line-strong read-only:text-ink-3"
              />
            </label>
          </>
        ) : email ? (
          <p className="text-[12px] text-ink-3">Select this contact to generate the first draft.</p>
        ) : (
          <p className="text-[12px] text-ink-3">Find a recruiter before drafting this email.</p>
        )}

        {target.error_code && (
          <p className="flex items-start gap-2 border-l-2 border-hot bg-[color-mix(in_srgb,var(--hot)_8%,transparent)] px-3 py-2 text-[12px] text-hot">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {target.error_detail || target.error_code}
          </p>
        )}

        {editable && hasDraft && (
          <fieldset className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
            <legend className="col-span-full text-[10px] font-semibold uppercase text-ink-3">Compliance review</legend>
            <PolicyInput label="Sender jurisdiction" value={senderJurisdiction} onChange={(value) => { setSenderJurisdiction(value); setDirty(true) }} />
            <PolicyInput label="Recipient jurisdiction" value={recipientJurisdiction} onChange={(value) => { setRecipientJurisdiction(value); setDirty(true) }} />
            <PolicySelect label="Recipient kind" value={recipientKind} onChange={(value) => { setRecipientKind(value); setDirty(true) }} options={[
              ['prior_inbound_recruiter', 'Prior inbound recruiter'],
              ['employer_published', 'Employer-published address'],
              ['verified_business_contact', 'Verified business contact'],
              ['role_inbox', 'Role inbox'],
            ]} />
            <PolicyInput label="Contact provenance date" value={provenanceAt} onChange={(value) => { setProvenanceAt(value); setDirty(true) }} placeholder="2026-07-28T10:00:00Z" />
            <PolicySelect label="Basis" value={basis} onChange={(value) => { setBasis(value); setDirty(true) }} options={[
              ['consent', 'Consent'],
              ['existing_relationship', 'Existing relationship'],
              ['legitimate_interest', 'Legitimate interest'],
            ]} />
            <PolicySelect label="Consent" value={consent} onChange={(value) => { setConsent(value); setDirty(true) }} options={[
              ['yes', 'Yes'], ['no', 'No'], ['not_applicable', 'Not applicable'],
            ]} />
            <PolicySelect label="Opt-out method" value={optOutMethod} onChange={(value) => { setOptOutMethod(value); setDirty(true) }} options={[
              ['reply', 'Reply'], ['mailto', 'Mailto'], ['unsubscribe_link', 'Unsubscribe link'],
            ]} />
            <PolicyInput label="Reviewer" value={reviewer} onChange={(value) => { setReviewer(value); setDirty(true) }} />
            <label className="col-span-full flex items-center gap-2 text-[11px] text-ink-2">
              <input type="checkbox" checked={identityFooter} onChange={(event) => { setIdentityFooter(event.target.checked); setDirty(true) }} />
              Sender identity and required footer are present in this exact draft.
            </label>
          </fieldset>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {target.error_code === 'transient_bounce' && (
            <>
              <ActionButton label="Confirmed delivered" onClick={() => resolveFeedback('delivered')} busy={busy === 'feedback_delivered'} Icon={Check} primary />
              <ActionButton label="Confirmed hard bounce" onClick={() => resolveFeedback('hard_bounce')} busy={busy === 'feedback_hard_bounce'} Icon={AlertTriangle} />
            </>
          )}
          {deliveryUnknown && (
            <>
              <ActionButton label="Check Sent" onClick={reconcileUnknown} busy={busy === 'reconcile_sent'} Icon={MailSearch} primary />
              <ActionButton label="Confirmed in Sent" onClick={() => resolveUnknown('sent')} busy={busy === 'resolve_sent'} Icon={Check} primary />
              <ActionButton label="Confirmed not sent" onClick={() => resolveUnknown('not_sent')} busy={busy === 'resolve_not_sent'} Icon={RefreshCw} />
            </>
          )}
          {editable && email && (target.state !== 'approved' || dirty) && (
            <ActionButton label={hasDraft ? 'Save draft' : 'Generate draft'} onClick={saveOnly} busy={busy === 'save'} Icon={Check} />
          )}
          {editable && hasDraft && email && (target.state !== 'approved' || dirty) && (
            <ActionButton label="Approve" onClick={approve} busy={busy === 'approve'} Icon={ShieldCheck} primary />
          )}
          {target.state === 'approved' && !dirty && !deliveryUnknown && (
            <ActionButton label="Send now" onClick={sendNow} busy={busy === 'send_now'} Icon={Send} primary />
          )}
          {editable && (
            <ActionButton label="Skip" onClick={skip} busy={busy === 'skip'} Icon={SkipForward} danger />
          )}
          {target.scheduled_at && target.state === 'approved' && (
            <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-ink-3">
              <Clock3 size={13} /> {formatDate(target.scheduled_at)}
            </span>
          )}
        </div>
      </div>
    </section>
  )
}

async function checkedAction(
  token: string,
  payload: Record<string, unknown> & { action: string },
): Promise<CampaignActionResult> {
  const result = await campaignAction(token, payload)
  if (!result.ok) throw new Error(result.error || messageForCode(result.code))
  return result
}

function messageForCode(code?: string): string {
  const messages: Record<string, string> = {
    campaign_inactive: 'Start the campaign before sending',
    approval_required: 'Approve this exact draft before sending',
    not_due: 'This approved email is not due yet',
    outside_send_window: 'Sending is outside the configured local time window',
    daily_limit: 'The daily campaign limit has been reached',
    minimum_spacing: 'The minimum spacing between emails has not elapsed',
    sending_disabled: 'Enable outreach and SMTP before sending',
    operation_busy: 'Another refresh or outreach operation is running',
    send_in_progress: 'Another campaign email is already being sent',
    delivery_unknown: 'A delivery outcome is unknown; check Sent mail before sending anything else',
    smtp_pre_send_failure: 'SMTP failed before submission; review configuration and approve again',
    smtp_transient_rejection: 'The SMTP server temporarily rejected submission; review before retrying',
    smtp_permanent_rejection: 'The SMTP server permanently rejected submission; correct the draft or recipient',
    multiple_sent_matches: 'Multiple exact Message-ID copies were found; sending remains blocked for manual review',
    sent_account_unconfigured: 'Configure the SMTP sender as exactly one read-only inbox account',
    inbox_disabled: 'Enable the read-only inbox before checking Sent mail',
    sent_folder_unavailable: 'The configured Sent folder is unavailable',
    sent_search_failed: 'The Sent folder could not be searched safely',
    sent_search_too_broad: 'The Sent search returned too many candidates; sending remains blocked',
    sent_reconciliation_failed: 'Could not safely check Sent mail; sending remains blocked',
    resume_changed: 'The approved résumé changed; review and approve this draft again',
    company_cooldown: 'This company is still in its outreach cooldown',
    nothing_due: 'No approved email is due',
  }
  return messages[code || ''] || code?.replaceAll('_', ' ') || 'Campaign action failed'
}

function TargetRow({ target, followup, selected, onSelect }: { target: CampaignTarget; followup: boolean; selected: boolean; onSelect: () => void }) {
  const recipientStatus = target.recipient_locked
    ? 'Original locked'
    : target.selected_email
      ? 'Verified contact'
      : 'Needs contact'
  return (
    <tr className={`border-t border-line ${selected ? 'bg-brand-weak' : 'hover:bg-inset/50'}`}>
      <td className="px-4 py-3 font-mono text-[14px] font-semibold text-ink">
        {followup ? `${Math.round(target.rank_score)}d` : target.rank_score.toFixed(1)}
      </td>
      <td className="px-3 py-3">
        <button type="button" onClick={onSelect} className="group flex w-full items-center justify-between gap-2 text-left">
          <span className="min-w-0">
            <strong className="block truncate text-[13px] font-semibold text-ink">{target.company}</strong>
            <span className="block truncate text-[10px] text-ink-3">
              {followup && target.evidence.anchor
                ? `Due since ${formatDate(target.evidence.anchor)}`
                : `${(target.evidence_coverage * 100).toFixed(0)}% evidence`}
            </span>
          </span>
          <ArrowRight size={13} className="shrink-0 text-ink-3" />
        </button>
      </td>
      <td className="px-3 py-3 font-mono text-[11px] text-ink-2">
        {followup
          ? (target.source_target_id ? 'Prior cold email' : 'Application')
          : `${(target.region_score * 100).toFixed(0)} / ${(target.compensation_score * 100).toFixed(0)} / ${(target.growth_score * 100).toFixed(0)}`}
      </td>
      <td className="max-w-44 px-3 py-3 text-[11px] text-ink-3">
        <span className="block truncate">{target.selected_email || `${target.contacts.length} candidate${target.contacts.length === 1 ? '' : 's'}`}</span>
        {followup && <span className="block text-[9px] font-semibold uppercase text-ink-3">{recipientStatus}</span>}
      </td>
      <td className="px-3 py-3"><StateBadge state={targetDisplayState(target)} /></td>
    </tr>
  )
}

function CampaignRow({ campaign, selected, onSelect }: { campaign: CampaignSummary; selected: boolean; onSelect: () => void }) {
  return (
    <li data-outreach-row className="border-b border-line">
      <button type="button" onClick={onSelect} aria-current={selected ? 'true' : undefined} className={`group relative grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-5 py-3 text-left outline-none transition-colors hover:bg-inset/60 focus-visible:bg-inset ${selected ? 'bg-brand-weak shadow-[inset_3px_0_var(--brand-coral)]' : ''}`}>
        <span className="min-w-0">
          <span className="mb-1 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: campaign.purpose === 'followup' ? 'var(--signal)' : 'var(--brand-coral)' }} aria-hidden="true" />
            <span className="text-[9px] font-semibold uppercase" style={{ color: campaign.purpose === 'followup' ? 'var(--signal)' : 'var(--brand-coral)' }}>
              {campaign.purpose === 'followup' ? 'Follow-up' : 'Cold'}
            </span>
          </span>
          <strong className="block truncate text-[13px] font-semibold text-ink">{campaign.name}</strong>
          <span className="mt-0.5 block text-[11px] text-ink-3">{campaign.target_count} targets · {campaign.counts.approved ?? 0} approved · {campaign.delivered_count} sent · {campaign.response_count} replies</span>
        </span>
        <StateBadge state={campaign.status} />
      </button>
    </li>
  )
}

function Evidence({ label, score, lines = [] }: { label: string; score: number; lines?: string[] }) {
  return (
    <section className="border-b border-line px-5 py-4 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[9px] font-semibold uppercase text-ink-3">{label}</p>
        <strong className="font-mono text-[14px] text-ink">{(score * 100).toFixed(0)}</strong>
      </div>
      <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-ink-3">{lines[0] || 'No direct evidence available'}</p>
    </section>
  )
}

function ContactNote({ contact }: { contact?: CampaignContact }) {
  if (!contact) return null
  return <p className="text-[11px] text-ink-3">{contact.note || contact.source} · {contact.confidence} confidence</p>
}

function PolicyInput({ label, value, onChange, placeholder = '' }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="text-[10px] font-semibold uppercase text-ink-3">
      {label}
      <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-line bg-inset px-3 text-[12px] font-normal normal-case text-ink outline-none focus:border-line-strong" />
    </label>
  )
}

function PolicySelect<T extends string>({ label, value, onChange, options }: { label: string; value: T | ''; onChange: (value: T | '') => void; options: Array<[T, string]> }) {
  return (
    <label className="text-[10px] font-semibold uppercase text-ink-3">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value as T | '')} className="mt-1 h-9 w-full rounded-md border border-line bg-inset px-3 text-[12px] font-normal normal-case text-ink outline-none focus:border-line-strong">
        <option value="">Select</option>
        {options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}
      </select>
    </label>
  )
}

function targetDisplayState(target: CampaignTarget): string {
  return target.error_code === 'delivery_unknown' ? 'delivery_unknown' : target.state
}

function StateBadge({ state }: { state: string }) {
  const positive = ['active', 'approved', 'sent', 'replied'].includes(state)
  const warning = ['failed', 'opted_out', 'cancelled'].includes(state)
  return (
    <span className={`inline-flex w-fit whitespace-nowrap rounded-full px-2 py-1 text-[9px] font-semibold uppercase ${positive ? 'bg-[color-mix(in_srgb,var(--strong)_14%,transparent)] text-strong' : warning ? 'bg-[color-mix(in_srgb,var(--hot)_10%,transparent)] text-hot' : 'bg-inset text-ink-3'}`}>
      {state.replaceAll('_', ' ')}
    </span>
  )
}

function ActionButton({ label, onClick, busy, Icon, primary = false, danger = false }: { label: string; onClick: () => void; busy: boolean; Icon: typeof Send; primary?: boolean; danger?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={busy} className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-[11px] font-medium disabled:opacity-50 ${primary ? 'border-brand bg-brand text-white' : danger ? 'border-line text-hot' : 'border-line text-ink-2 hover:border-line-strong hover:text-ink'}`}>
      {busy ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />}{label}
    </button>
  )
}

function NumberInput({ label, value, onChange, min, max }: { label: string; value: number; onChange: (value: number) => void; min: number; max: number }) {
  return (
    <label className="text-[9px] font-semibold uppercase text-ink-3">
      <span className="mb-1 block">{label}</span>
      <input type="number" aria-label={label} min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} className="h-9 w-full rounded-md border border-line bg-inset px-2 font-mono text-[12px] font-normal normal-case text-ink outline-none focus:border-line-strong" />
    </label>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><span className="block text-[9px] uppercase text-ink-3">{label}</span><strong className="font-mono text-lg text-ink">{value}</strong></div>
}

function Loading({ label }: { label: string }) {
  return <div className="flex h-full items-center justify-center gap-2 text-[12px] text-ink-3"><Loader2 size={15} className="animate-spin" />{label}</div>
}

function EmptyCampaigns() {
  return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><ShieldCheck size={28} className="text-ink-3" /><p className="mt-3 text-[14px] font-medium text-ink">No outreach batches yet</p></div>
}

function NoCampaign() {
  return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><Send size={28} className="text-ink-3" /><p className="mt-3 text-[14px] font-medium text-ink">Select an outreach batch</p></div>
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export function CampaignsUnavailable() {
  return (
    <section className="mx-auto flex min-h-full max-w-[900px] items-center justify-center px-6 py-16 text-center">
      <div>
        <ShieldCheck size={30} className="mx-auto text-ink-3" />
        <h2 className="mt-4 text-lg font-semibold text-ink">Outreach stays in your private workspace</h2>
        <p className="mt-2 text-[13px] text-ink-3">Open Jobscope through <code className="font-mono text-ink-2">jobscope serve</code> to review approvals and scheduled email.</p>
      </div>
    </section>
  )
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || path
}

function FollowupFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-line px-5 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0 sm:px-7">
      <p className="text-[9px] font-semibold uppercase text-ink-3">{label}</p>
      <p className="mt-1 text-[12px] font-medium text-ink">{value}</p>
    </div>
  )
}

export function CampaignsSnapshotView({
  snapshot,
  selectedId,
  onSelect,
}: {
  snapshot: OutreachSnapshot
  selectedId?: string
  onSelect: (campaignId?: string) => void
}) {
  const selected = snapshot.campaigns.find((campaign) => campaign.id === selectedId)
    ?? snapshot.campaigns[0]
  const detail = snapshot.details.find((item) => item.campaign_id === selected?.id)
  const approved = snapshot.campaigns.reduce(
    (sum, campaign) => sum + (campaign.counts.approved ?? 0), 0,
  )
  const sent = snapshot.campaigns.reduce((sum, campaign) => sum + campaign.delivered_count, 0)
  const replies = snapshot.campaigns.reduce((sum, campaign) => sum + campaign.response_count, 0)
  const privateUrl = `${privateWorkspaceOrigin()}/#/?view=campaigns${
    selected ? `&campaign=${encodeURIComponent(selected.id)}` : ''
  }`
  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <WorkspaceHeader
        eyebrow={<span className="flex items-center gap-1.5"><ShieldCheck size={13} aria-hidden="true" /> Read-only encrypted snapshot</span>}
        title="Outreach"
        description="Review campaign state and delivery history. Open the private control plane to make changes or send mail."
        actions={(
          <div className="flex gap-5 border-l border-line pl-4 text-right">
            <Metric label="Batches" value={snapshot.campaigns.length} />
            <Metric label="Approved" value={approved} />
            <Metric label="Sent" value={sent} />
            <Metric label="Replies" value={replies} />
          </div>
        )}
        accent="brand"
      />
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line bg-inset/35 px-4 py-3 sm:px-7">
        <ShieldCheck size={15} className="shrink-0 text-brand" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold text-ink">Pages is view-only</p>
          <p className="text-[11px] text-ink-3">Delete draft · Find recruiters · Approve · Start · Check replies and due work</p>
        </div>
        <a
          href={privateUrl}
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-brand bg-panel px-3 text-[12px] font-semibold text-brand hover:bg-brand-weak"
        >
          Open private workspace <ArrowRight size={13} aria-hidden="true" />
        </a>
      </div>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(250px,.48fr)_minmax(0,1.52fr)]">
        <div className="min-h-0 overflow-auto border-r border-line">
          {snapshot.campaigns.length ? (
            <ul>{snapshot.campaigns.map((campaign) => (
              <CampaignRow
                key={campaign.id}
                campaign={campaign}
                selected={campaign.id === selected?.id}
                onSelect={() => onSelect(campaign.id)}
              />
            ))}</ul>
          ) : <EmptyCampaigns />}
        </div>
        <div className="min-h-0 overflow-auto">
          {selected ? (
            <div>
              <header className="border-b border-line px-5 py-5 sm:px-7">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xl font-semibold text-ink">{selected.name}</h3>
                  <StateBadge state={selected.status} />
                </div>
                <p className="mt-1 text-[12px] text-ink-3">
                  {selected.target_count} targets · updated {formatDate(selected.updated_at)}
                </p>
              </header>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[680px] border-collapse text-left">
                  <thead className="bg-inset text-[9px] font-semibold uppercase text-ink-3">
                    <tr><th className="px-5 py-2 sm:px-7">Company</th><th className="px-3 py-2">Recipient</th><th className="px-3 py-2">Subject</th><th className="px-3 py-2">Schedule</th><th className="px-3 py-2">State</th></tr>
                  </thead>
                  <tbody>{(detail?.targets ?? []).map((target) => (
                    <SnapshotTargetRow key={target.id} target={target} />
                  ))}</tbody>
                </table>
                {!detail?.targets.length && <p className="px-5 py-10 text-center text-[13px] text-ink-3">No targets in this campaign snapshot.</p>}
              </div>
            </div>
          ) : <NoCampaign />}
        </div>
      </div>
    </section>
  )
}

function SnapshotTargetRow({ target }: { target: CampaignSnapshotTarget }) {
  return (
    <tr className="border-t border-line text-[11px]">
      <td className="px-5 py-3 font-semibold text-ink sm:px-7">{target.company}</td>
      <td className="max-w-48 truncate px-3 py-3 text-ink-2" title={target.selected_email}>{target.selected_email || 'Needs contact'}</td>
      <td className="max-w-64 truncate px-3 py-3 text-ink-3" title={target.subject}>{target.subject || 'No draft subject'}</td>
      <td className="px-3 py-3 text-ink-3">{target.scheduled_at ? formatDate(target.scheduled_at) : 'Unscheduled'}</td>
      <td className="px-3 py-3"><StateBadge state={target.error_code || target.state} /></td>
    </tr>
  )
}