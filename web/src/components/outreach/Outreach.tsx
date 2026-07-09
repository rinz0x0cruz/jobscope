import type { AppliedCompany, Profile } from '@/lib/schema'
import { ProfileCard } from './ProfileCard'
import { CompanySearch } from './CompanySearch'
import { AppliedOutreach } from './AppliedOutreach'

/** Cold-outreach workspace. Surfaces your résumé profile, HR contacts for the
 *  companies you've applied to (pre-computed at refresh, behind the unlock), and a
 *  live company search (discovery + send under `jobscope serve`; mailto on Pages). */
export function Outreach({ profile, applied }: { profile: Profile | null; applied: AppliedCompany[] }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-mute">
        Your cold-outreach workspace — the résumé profile that drives matching, HR contacts at
        companies you've applied to, and a live company search with a résumé-attached draft.
      </p>
      <ProfileCard profile={profile} />
      <AppliedOutreach applied={applied} profile={profile} />
      <CompanySearch />
    </div>
  )
}
