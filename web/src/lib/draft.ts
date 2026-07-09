import type { Profile } from './schema'

// Client-side cold-intro draft for the applied-companies cards. On the published
// site there's no backend to build a tailored draft (that needs the résumé + AI),
// so we compose a short, honest intro from the unlocked profile and hand it to the
// user's own mail client via mailto: (which also carries their signature). The
// résumé is attached by the user in their client — mailto can't attach files.
export function draftSubject(company: string, profile: Profile | null): string {
  const role = profile?.search_terms?.[0]
  return role ? `Introduction — ${role} at ${company}` : `Introduction — ${company}`
}

export function draftBody(company: string, profile: Profile | null): string {
  const seniority = profile?.seniority ? `${profile.seniority} ` : ''
  const years = profile?.years_experience ? `~${profile.years_experience} years' ` : ''
  const skills = (profile?.top_skills || []).slice(0, 4).join(', ')
  const skillLine = skills ? ` in ${skills}` : ''
  return [
    'Hello,',
    '',
    `I recently applied to ${company} and wanted to reach out directly. I'm a ${seniority}candidate ` +
      `with ${years}experience${skillLine}.`,
    '',
    "I'd welcome the chance to discuss how I can contribute — I've attached my résumé for your reference.",
    '',
    'Thank you for your time.',
  ].join('\n')
}

export function mailtoHref(to: string, company: string, profile: Profile | null): string {
  const subject = encodeURIComponent(draftSubject(company, profile))
  const body = encodeURIComponent(draftBody(company, profile))
  return `mailto:${to}?subject=${subject}&body=${body}`
}
