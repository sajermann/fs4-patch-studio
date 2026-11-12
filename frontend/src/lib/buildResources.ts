import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { MachineInfo } from '@/api/types'
import type { MessageKey } from '@/i18n/pt-BR'

/** The build settings of the config (null = the defaults). */
export interface BuildResourcesValue {
  build_cores?: number | null
  build_memory_percent?: number | null
}

/** Cores and memory of this machine (GET /api/machine). */
export function useMachine() {
  return useQuery({ queryKey: ['machine'], queryFn: api.machine }).data
}

/** Worker processes the build will use: the same rule as fsmod.workers.plan (unknown cores or memory -> 1). */
export function plannedWorkers(machine: MachineInfo, value: BuildResourcesValue) {
  if (!machine.cores || !machine.memory_mb) return 1
  const cores = value.build_cores ? Math.max(1, Math.min(value.build_cores, machine.cores)) : machine.default_cores
  const [low, high] = machine.memory_percent_range
  const percent = Math.max(low, Math.min(value.build_memory_percent ?? machine.default_memory_percent, high))
  const fits = Math.floor((machine.memory_mb * percent) / 100 / machine.worker_memory_mb)
  return Math.max(1, Math.min(cores, fits))
}

/** What is wrong with the settings (message keys of the fields), empty when they can be saved. The backend brings
 * out-of-range values into range anyway; this tells the user before saving. */
export function buildResourcesErrors(machine: MachineInfo | undefined, value: BuildResourcesValue) {
  const errors: { cores?: MessageKey; memory?: MessageKey } = {}
  const cores = value.build_cores
  if (cores != null && (!Number.isInteger(cores) || cores < 1 || (machine?.cores != null && cores > machine.cores)))
    errors.cores = 'buildResources.coresOutOfRange'
  const percent = value.build_memory_percent
  const [low, high] = machine?.memory_percent_range ?? [10, 90]
  if (percent != null && (!Number.isInteger(percent) || percent < low || percent > high))
    errors.memory = 'buildResources.memoryOutOfRange'
  return errors
}
