export interface FitMetric {
  label: string
  value: number
}

export interface FitPresentation {
  metrics: FitMetric[]
  skills: string[]
  company: string
  warning: string
  route: string
  fallback: string
}

export type DescriptionBlock =
  | { type: 'heading'; text: string }
  | { type: 'bullet'; text: string }
  | { type: 'paragraph'; text: string }

const METRIC_LABELS: Record<string, string> = {
  company: 'Company',
  location: 'Location',
  recency: 'Recency',
  seniority: 'Seniority',
  skills: 'Skills',
}

function sentenceCase(value: string): string {
  const text = value.trim()
  return text ? text[0].toUpperCase() + text.slice(1) : ''
}

export function presentFitRationale(rationale: string): FitPresentation {
  const [scoreText, routeText = ''] = rationale.split(/\s+→\s+/, 2)
  const presentation: FitPresentation = {
    metrics: [],
    skills: [],
    company: '',
    warning: '',
    route: '',
    fallback: rationale.trim(),
  }

  for (const segment of scoreText.split(/\s*\|\s*/)) {
    const part = segment.trim()
    if (part.toLowerCase().startsWith('top:')) {
      presentation.metrics = part
        .slice(part.indexOf(':') + 1)
        .split(',')
        .map((metric) => /^(.+?)\s+(\d+)%$/.exec(metric.trim()))
        .filter((match): match is RegExpExecArray => match !== null)
        .map((match) => ({
          label: METRIC_LABELS[match[1].toLowerCase()] ?? sentenceCase(match[1]),
          value: Number(match[2]),
        }))
    } else if (part.toLowerCase().startsWith('skills matched:')) {
      presentation.skills = part
        .slice(part.indexOf(':') + 1)
        .split(',')
        .map((skill) => skill.trim())
        .filter(Boolean)
    } else if (part.toLowerCase().startsWith('company:')) {
      presentation.company = sentenceCase(part.slice(part.indexOf(':') + 1))
    } else if (part.startsWith('⚠')) {
      presentation.warning = part.replace(/^⚠\s*/, '').trim()
    }
  }

  const route = routeText.trim()
  if (route) {
    const match = /^(?:tailor from )?(.+?)\s+\((technical|advisory) role\)$/i.exec(route)
    presentation.route = match
      ? `${sentenceCase(match[1])} résumé · ${sentenceCase(match[2])} role`
      : sentenceCase(route)
  }
  return presentation
}

function cleanDescriptionText(text: string): string {
  return text
    .replace(/\r/g, '')
    .replace(/\\([\\|*#_+&-])/g, '$1')
    .replace(/\*\*([^*\n]+)\*\*\s*:?/g, '\n@@heading@@$1\n')
    .replace(/\*\*([^*\n]+)\*\*/g, '$1')
    .replace(/[ \t]+\n/g, '\n')
}

export function presentJobDescription(text: string): DescriptionBlock[] {
  const blocks: DescriptionBlock[] = []
  for (const rawLine of cleanDescriptionText(text).split('\n')) {
    const line = rawLine.trim()
    if (!line) continue
    if (line.startsWith('@@heading@@')) {
      blocks.push({ type: 'heading', text: line.slice('@@heading@@'.length).trim() })
      continue
    }
    if (/^[*•-]\s*/.test(line)) {
      blocks.push({ type: 'bullet', text: line.replace(/^[*•-]\s*/, '').trim() })
      continue
    }
    if (line.length <= 60 && /:$/.test(line)) {
      blocks.push({ type: 'heading', text: line.slice(0, -1).trim() })
      continue
    }
    blocks.push({ type: 'paragraph', text: line })
  }
  return blocks
}