import { Field, NumberInput } from '@/components/common/form'
import { useI18n } from '@/i18n'
import { buildResourcesErrors, plannedWorkers, useMachine, type BuildResourcesValue } from '@/lib/buildResources'

/** How much of the machine the build may use: cores and percent of the memory (empty = the defaults). Used in the
 * settings and, collapsed, in the first-run setup; the pages block saving while buildResourcesErrors finds any. */
export function BuildResourcesFields({
  value,
  onChange,
}: {
  value: BuildResourcesValue
  onChange: (patch: BuildResourcesValue) => void
}) {
  const { t } = useI18n()
  const machine = useMachine()
  const cores = machine?.cores
  const [low, high] = machine?.memory_percent_range ?? [10, 90]
  const memoryGb = machine?.memory_mb ? (machine.memory_mb / 1024).toFixed(1) : null
  const errors = buildResourcesErrors(machine, value)
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={t('buildResources.cores')}
          hint={cores ? t('buildResources.coresHint', { cores, default: machine.default_cores }) : t('buildResources.coresUnknown')}
        >
          <NumberInput
            value={value.build_cores ?? undefined}
            min={1}
            max={cores ?? undefined}
            placeholder={t('buildResources.automatic', { value: machine?.default_cores ?? 1 })}
            onChange={(v) => onChange({ build_cores: v ?? null })}
          />
          {errors.cores && <p className="text-xs text-destructive">{t(errors.cores, { max: cores ?? 1 })}</p>}
        </Field>
        <Field
          label={t('buildResources.memory')}
          hint={memoryGb ? t('buildResources.memoryHint', { memory: memoryGb, low, high }) : t('buildResources.memoryUnknown')}
        >
          <NumberInput
            value={value.build_memory_percent ?? undefined}
            min={low}
            max={high}
            placeholder={t('buildResources.automatic', { value: `${machine?.default_memory_percent ?? 50}%` })}
            onChange={(v) => onChange({ build_memory_percent: v ?? null })}
          />
          {errors.memory && <p className="text-xs text-destructive">{t(errors.memory, { low, high })}</p>}
        </Field>
      </div>
      {machine && !errors.cores && !errors.memory && (
        <p className="text-sm text-muted-foreground">{t('buildResources.summary', { workers: plannedWorkers(machine, value) })}</p>
      )}
    </div>
  )
}
