import type { Profile } from '@/lib/schema'
import { ProfileCard } from './ProfileCard'

/** Cold-outreach workspace. Slice 1: surfaces your résumé profile. Next: a company
 *  search that finds HR/recruiting emails and drafts an email with your résumé
 *  attached (live discovery under `jobscope serve`; mailto on the published site). */
export function Outreach({ profile }: { profile: Profile | null }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-mute">
        Your cold-outreach workspace — the résumé profile that drives matching and
        outreach, and (next) company HR-email search with a résumé-attached draft.
      </p>
      <ProfileCard profile={profile} />
    </div>
  )
}
