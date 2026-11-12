/** Web links typed for credits, with the same rule as the backend (fsmod.weblink.normalize): only http(s) addresses;
 * one without a scheme ('site.com/x') gets https://. Returns null when the text is not a web address. */
export function normalizeWebLink(text: string): string | null {
  let url = text.trim()
  if (!url || /\s/.test(url)) return null
  if (!url.includes('://')) {
    const head = url.split('/', 1)[0]
    if (head.includes(':') && !/^\d+$/.test(head.slice(head.lastIndexOf(':') + 1))) return null // mailto:, javascript:
    url = `https://${url}`
  }
  try {
    const parsed = new URL(url)
    const host = parsed.hostname
    if (!['http:', 'https:'].includes(parsed.protocol) || !host || (!host.includes('.') && host !== 'localhost')) return null
  } catch {
    return null
  }
  return url
}
