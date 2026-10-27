import { Eye, EyeOff, Lock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'

/** Show / hide toggle for table rows (the row itself is a link, so the click does not reach it). */
export function HideButton({ hidden, onToggle, hideHint, showHint }: { hidden: boolean; onToggle: () => void; hideHint: string; showHint: string }) {
  const { t } = useI18n()
  return (
    <Button
      variant="ghost"
      size="sm"
      className="min-w-24 justify-start" // same width for "hide" and "show": the columns do not move
      title={hidden ? showHint : hideHint}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
    >
      {hidden ? <Eye /> : <EyeOff />} {hidden ? t('list.show') : t('list.hide')}
    </Button>
  )
}

/** "Not in the patch" badge for hidden project leagues/teams. */
export function OutOfPatchBadge({ label }: { label?: string }) {
  const { t } = useI18n()
  return (
    <Badge variant="outline" className="ml-2 font-normal">
      {label ?? t('list.outOfPatch')}
    </Badge>
  )
}

/** League the game itself hides (in its code), or a team of one: unlike "hidden by the project" there is no
 * button to show it. */
export function GameHiddenBadge({ team = false }: { team?: boolean }) {
  const { t } = useI18n()
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="secondary" className="ml-1 gap-1 font-normal text-amber-700 dark:text-amber-400">
          <Lock className="size-3" /> {team ? t('list.leagueHiddenInGame') : t('list.hiddenInGame')}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {t('list.hiddenInGameHint')}
      </TooltipContent>
    </Tooltip>
  )
}
