import type { MessageKey } from '@/i18n'

// Interface labels (dictionary keys) for codes used by the game data.

export const APPEARANCE_LABELS: Record<string, MessageKey> = {
  headtypecode: 'appearance.headtypecode',
  hairtypecode: 'appearance.hairtypecode',
  haircolorcode: 'appearance.haircolorcode',
  skintonecode: 'appearance.skintonecode',
  skintypecode: 'appearance.skintypecode',
  facialhairtypecode: 'appearance.facialhairtypecode',
  facialhaircolorcode: 'appearance.facialhaircolorcode',
  eyecolorcode: 'appearance.eyecolorcode',
  eyebrowcode: 'appearance.eyebrowcode',
  sideburnscode: 'appearance.sideburnscode',
  bodytypecode: 'appearance.bodytypecode',
  shoetypecode: 'appearance.shoetypecode',
  gkglovetypecode: 'appearance.gkglovetypecode',
  jerseysleevelengthcode: 'appearance.jerseysleevelengthcode',
  socklengthcode: 'appearance.socklengthcode',
}

export const SKILL_LABELS: Record<string, MessageKey> = {
  ATH: 'skill.ATH',
  DEF: 'skill.DEF',
  DRI: 'skill.DRI',
  GK: 'skill.GK',
  PAS: 'skill.PAS',
  SHO: 'skill.SHO',
  SPE: 'skill.SPE',
  TRI: 'skill.TRI',
  overall: 'skill.overall',
}

export const KIT_LABELS = { home: 'kit.home', away: 'kit.away' } as const satisfies Record<string, MessageKey>
export const KIT_PART_LABELS = { jersey: 'kit.jersey', shorts: 'kit.shorts', socks: 'kit.socks' } as const satisfies Record<
  string,
  MessageKey
>
export const REAL_KIT_LABELS = { home: 'kit.home', away: 'kit.away', goalkeeper: 'kit.goalkeeper' } as const satisfies Record<
  string,
  MessageKey
>

/** teamkits number color palette (same as FIFA); swatches are approximate (the game keeps only the index). */
export const NUMBER_COLORS: { value: number; label: MessageKey; hex: string }[] = [
  { value: 1, label: 'color.white', hex: '#f2f2f2' },
  { value: 2, label: 'color.black', hex: '#0c0c0c' },
  { value: 3, label: 'color.blue', hex: '#0047b6' },
  { value: 4, label: 'color.red', hex: '#a60005' },
  { value: 5, label: 'color.yellow', hex: '#f0da28' },
  { value: 6, label: 'color.green', hex: '#007b00' },
  { value: 7, label: 'color.orange', hex: '#ff8700' },
  { value: 8, label: 'color.purple', hex: '#7f19be' },
  { value: 9, label: 'color.brown', hex: '#55310e' },
  { value: 10, label: 'color.pink', hex: '#f481b5' },
  { value: 11, label: 'color.maroon', hex: '#770f05' },
  { value: 12, label: 'color.lightBlue', hex: '#82c4f6' },
  { value: 13, label: 'color.navy', hex: '#011452' },
  { value: 14, label: 'color.gray', hex: '#a4a4a4' },
  { value: 15, label: 'color.lightYellow', hex: '#cccc67' },
  { value: 16, label: 'color.gold', hex: '#9d884e' },
  { value: 17, label: 'color.goldenYellow', hex: '#ffcc33' },
  { value: 19, label: 'color.darkGreen', hex: '#003c00' },
]

export const FOOT_LABELS = { right: 'foot.right', left: 'foot.left' } as const satisfies Record<string, MessageKey>
