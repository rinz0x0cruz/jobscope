import { describe, expect, it } from 'vitest'
import { presentFitRationale, presentJobDescription } from '@/lib/jobPresentation'

describe('job presentation', () => {
  it('turns scorer rationale into readable fit data', () => {
    expect(
      presentFitRationale(
        'top: skills 100%, location 100%, recency 85% | company: notable | skills matched: incident response, python, aws → tailor from research (technical role)',
      ),
    ).toEqual({
      metrics: [
        { label: 'Skills', value: 100 },
        { label: 'Location', value: 100 },
        { label: 'Recency', value: 85 },
      ],
      skills: ['incident response', 'python', 'aws'],
      company: 'Notable',
      warning: '',
      route: 'Research résumé · Technical role',
      fallback:
        'top: skills 100%, location 100%, recency 85% | company: notable | skills matched: incident response, python, aws → tailor from research (technical role)',
    })
  })

  it('cleans escaped markdown into description blocks', () => {
    expect(
      presentJobDescription(
        'Hiring Now\\| Security Engineer\n\n**Key Responsibilities**:\n\\*Manage day\\-to\\-day operations\n- Review alerts\nRequired Skills:\nPython and AWS',
      ),
    ).toEqual([
      { type: 'paragraph', text: 'Hiring Now| Security Engineer' },
      { type: 'heading', text: 'Key Responsibilities' },
      { type: 'bullet', text: 'Manage day-to-day operations' },
      { type: 'bullet', text: 'Review alerts' },
      { type: 'heading', text: 'Required Skills' },
      { type: 'paragraph', text: 'Python and AWS' },
    ])
  })
})