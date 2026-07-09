import { useEffect, useState } from 'react'
import type { AppliedCompany, Profile } from '@/lib/schema'
import { localServeToken } from '@/lib/outreach'
import { ProfileCard } from './ProfileCard'
import { ResumeUpload } from './ResumeUpload'
import { CompanySearch } from './CompanySearch'
import { AppliedOutreach } from './AppliedOutreach'

/** Cold-outreach workspace. Surfaces your résumé profile (with an upload under local
 *  serve), HR contacts for the companies you've applied to (pre-computed at refresh,
 *  behind the unlock), and a live company search (discovery + send under serve). */
export function Outreach({ profile: profileProp, applied }: { profile: Profile | null; applied: AppliedCompany[] }) {
  const [profile, setProfile] = useState<Profile | null>(profileProp)
  const [token, setToken] = useState<string | null>(null)

  useEffect(() => {
    setProfile(profileProp)
  }, [profileProp])

  useEffect(() => {
    let live = true
    localServeToken().then((t) => live && setToken(t))
    return () => {
      live = false
    }
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-mute">
        Your cold-outreach workspace — the résumé profile that drives matching, HR contacts at
        companies you've applied to, and a live company search with a résumé-attached draft.
      </p>
      <ProfileCard profile={profile} />
      {token && <ResumeUpload token={token} onUploaded={setProfile} />}
      <AppliedOutreach applied={applied} profile={profile} />
      <CompanySearch />
    </div>
  )
}
