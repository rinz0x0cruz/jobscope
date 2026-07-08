// Download an inline <svg> element as a standalone .svg file. CSS custom
// properties are resolved to their computed values first, because `var(--x)` is
// meaningless in a bare SVG document opened outside the app.
const SVG_NS = 'http://www.w3.org/2000/svg'

export function downloadSvg(svg: SVGSVGElement, filename: string): void {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', SVG_NS)

  const vb = (svg.getAttribute('viewBox') ?? '').split(/\s+/).map(Number)
  const [w, h] = vb.length === 4 ? [vb[2], vb[3]] : [800, 300]
  clone.setAttribute('width', String(w))
  clone.setAttribute('height', String(h))

  const rootStyle = getComputedStyle(document.documentElement)
  const resolveVars = (markup: string) =>
    markup.replace(/var\((--[a-z0-9-]+)\)/gi, (_m, name: string) =>
      rootStyle.getPropertyValue(name).trim() || 'currentColor')

  // Opaque background so light labels stay legible in any viewer.
  const bg = rootStyle.getPropertyValue('--bg').trim() || '#0b0f14'
  const rect = document.createElementNS(SVG_NS, 'rect')
  rect.setAttribute('x', '0')
  rect.setAttribute('y', '0')
  rect.setAttribute('width', String(w))
  rect.setAttribute('height', String(h))
  rect.setAttribute('fill', bg)
  clone.insertBefore(rect, clone.firstChild)

  const markup =
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    resolveVars(new XMLSerializer().serializeToString(clone))
  const blob = new Blob([markup], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}
