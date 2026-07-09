import type { Profile } from '@/lib/schema'
import { ProfileCard } from './ProfileCard'
import { CompanySearch } from './CompanySearch'

/** Cold-outreach workspace. Surfaces your résumé profile, then a company search that
 *  finds published HR/recruiting emails and drafts a résumé-attached email (live
 *  discovery + send under `jobscope serve`; mailto compose on the published site). */
export function Outreach({ profile }: { profile: Profile | null }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-mute">
        Your cold-outreach workspace — the résumé profile that drives matching, and a
        company search that finds HR emails and drafts a note with your résumé attached.
      </p>
      <ProfileCard profile={profile} />
      <CompanySearch />
    </div>
  )
}
