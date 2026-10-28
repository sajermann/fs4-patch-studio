import type { Catalog, KitKind, Player, PlayerDefaults, RealKitSlot, RGB, StreetPartName, StreetPiece, Team } from '@/api/types'
import type { PreviewAppearance, PreviewKit, PreviewOutfit } from '@/components/common/PlayerPreview'
import { fullKit } from '@/lib/teams'

export const STREET_PARTS: StreetPartName[] = ['top', 'bottom', 'socks']
export const GOALKEEPER_POSITION = 0 // teamplayerlinks.position of a goalkeeper (fsmod.catalog.POSITIONS)

/** Team kit the 3D preview dresses for a slot, as the build writes it: the real kit when the team uses real kits and
 * the slot has jersey and shorts, else the generic kit (an empty goalkeeper slot shows the generic home kit; the game
 * uses its own default there). No team: neutral grey. */
export function teamPreviewKit(team: Team | undefined, slot: RealKitSlot): PreviewKit {
  if (!team) return { jersey: [200, 200, 200], shorts: [60, 60, 60] }
  const kit = fullKit(team, slot === 'away' ? 'away' : 'home')
  const real = team.use_real_kits ? team.real_kits?.[slot] : undefined
  return {
    jersey: kit.jersey,
    shorts: kit.shorts,
    crest: team.crest,
    real: real?.jersey && real.shorts ? { jersey: real.jersey, shorts: real.shorts, collar: real.collar } : undefined,
  }
}

/** Values the 3D preview shows for a player: own value, else the template's, else the first valid code. */
export function previewAppearance(player: Player | undefined, defaults: PlayerDefaults | undefined, catalog: Catalog | undefined): PreviewAppearance {
  const options = catalog?.appearance ?? {}
  const code = (key: string) => player?.appearance[key] ?? defaults?.appearance[key] ?? options[key]?.[0] ?? 0
  return {
    headtypecode: code('headtypecode'),
    hairtypecode: code('hairtypecode'),
    hairColor: catalog?.hair_colors[code('haircolorcode')] ?? '#808080',
    eyecolorcode: code('eyecolorcode'),
    eyebrowcode: code('eyebrowcode'),
    sideburnscode: code('sideburnscode'),
    facialhaircolorcode: code('facialhaircolorcode'),
    facialhairtypecode: code('facialhairtypecode'),
    skintypecode: code('skintypecode'),
    skintonecode: code('skintonecode'),
    jerseysleevelengthcode: code('jerseysleevelengthcode'),
    socklengthcode: code('socklengthcode'),
    shoetypecode: code('shoetypecode'),
    gkglovetypecode: code('gkglovetypecode'),
    height: player?.height ?? defaults?.height ?? 180,
  }
}

/** Colors the builder writes for a street part the user did not customize (same rule as fsmod.builder):
 * primary = the part's kit color, secondary = trim (shorts use the jersey color, the others the shorts color). */
export function derivedStreetColors(team: Team, kind: KitKind, part: StreetPartName): [RGB, RGB, RGB] {
  const kit = fullKit(team, kind)
  const main = part === 'top' ? kit.jersey : part === 'bottom' ? kit.shorts : kit.socks
  const trim = part === 'bottom' ? kit.jersey : kit.shorts
  return [main, trim, main]
}

/** Street piece of a part: the user's choice, else the template's first piece with derived colors. */
export function streetPiece(team: Team, kind: KitKind, part: StreetPartName, catalog: Catalog | undefined): StreetPiece {
  const own = team.street_kits?.[kind]?.[part]
  if (own) return own
  const tpl = catalog?.template_street[team.template]?.[kind]?.[part]
  const styles = catalog?.street_options[part] ?? {}
  const style = tpl?.style ?? Number(Object.keys(styles)[0] ?? 0)
  const pattern = tpl?.pattern ?? styles[style]?.[0] ?? 0
  return { style, pattern, colors: derivedStreetColors(team, kind, part) }
}

export function streetOutfit(team: Team, kind: KitKind, catalog: Catalog | undefined): PreviewOutfit {
  const top = streetPiece(team, kind, 'top', catalog)
  const bottom = streetPiece(team, kind, 'bottom', catalog)
  return {
    kind: 'street',
    top,
    bottom,
    socks: streetPiece(team, kind, 'socks', catalog),
    arms: catalog?.street_arms[top.style] ?? 0,
    fullLength: catalog?.street_full_length_bottoms.includes(bottom.style) ?? false,
    crest: team.crest,
  }
}
