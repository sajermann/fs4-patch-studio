import type { Issue } from '@/api/types'
import { hasMessage, type TFunction } from '@/i18n'

/** Validation message in the interface language (by code + params), else the backend's pt-BR text. */
export function issueText(t: TFunction, issue: Issue) {
  const key = `issue.${issue.code}`
  return hasMessage(key) ? t(key, { entity: issue.entity, ...issue.params }) : issue.message
}
