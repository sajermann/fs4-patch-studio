import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { kitTextureUrl } from '@/api/client'
import type { RGB, StreetPiece } from '@/api/types'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

// Live 3D preview of a generic player (headclasscode 1), assembled like the game does (player.lua):
// head mesh + face texture (skin, eyebrows, beard baked in) + eyes + hair tinted by the hair color, and the body
// with the team kit (solid colors + crest decal, as the builder writes it; or a real kit: the FIFA 14-16 PNGs and
// their collar) or a street kit (color masks painted with 3 colors in the shader, like the game).
//
// A real face (FIFA 14 pack, headclasscode 0) replaces head and hair with the face converted by the backend exactly
// as the build converts it. 'far' shows what the normal play camera draws: the shared LOD head with the same face
// texture + the hairlod cap (player.lua, PlayerAssetLowLod).
//
// Each part (head, hair, jersey, shoes...) loads its mesh and textures on its own and keeps showing the previous
// version until the new one is ready, so changing one code only swaps that part (no Suspense, no blinking). A
// "Carregando…" badge shows while some new mesh/texture is on its way (a real face takes a few seconds to convert).

export interface PreviewAppearance {
  headtypecode: number
  hairtypecode: number
  hairColor: string // CSS color from the game's table
  eyecolorcode: number
  eyebrowcode: number
  sideburnscode: number
  facialhaircolorcode: number
  facialhairtypecode: number
  skintypecode: number
  skintonecode: number
  jerseysleevelengthcode: number
  socklengthcode: number
  shoetypecode: number
  gkglovetypecode: number
  height: number // cm; the game scales the whole player by it (validated in game, 165 x 200 cm)
}

export interface PreviewKit {
  jersey: RGB
  shorts: RGB // the socks are mapped on the shorts texture, so they show this color too
  crest?: string | null // project image path
  // real kit (lib/preview teamPreviewKit): project PNGs drawn instead of the solid colors, and its collar mesh
  real?: { jersey: string; shorts: string; collar: number }
}

/** What the player wears: the team kit or a street kit (arms = arms mesh for the top's sleeves). */
export type PreviewOutfit =
  | { kind: 'team'; kit: PreviewKit }
  | { kind: 'street'; top: StreetPiece; bottom: StreetPiece; socks: StreetPiece; arms: number; fullLength: boolean }

export type View = 'face' | 'body'
export type Distance = 'near' | 'far'

/** Converted real face: query of /api/preview/scanned/<file> (api/client scannedFaceQuery). */
export interface PreviewScannedFace {
  query: string
}
type Vec3 = [number, number, number]

// The game's hair_cm is a mid grey; its shader brightens the tint, so scale it up a little.
const HAIR_TINT_GAIN = 1.8
// player.lua: scanned heads get hairColor 0x808080 (their color comes from hair_cm)
const SCANNED_HAIR_COLOR = '#808080'
// Views for the reference model; the face view follows the head when the player is scaled, the body view stays
// fixed so height differences show.
const VIEWS: Record<View, { camera: Vec3; target: Vec3 }> = {
  // a bit above the eyes and a little back: the whole hair fits above the face (user's choice, 27/10)
  face: { camera: [0, 1.715, 0.66], target: [0, 1.7, 0] },
  body: { camera: [0, 1.02, 4.1], target: [0, 1.02, 0] },
}
// Top of the generic head in the reference pose (head mesh max y). Assumption: the game scales the skeleton so that
// this point ends at the player's height.
const MODEL_HEIGHT_CM = 183.6
const FOCUS_DISTANCE = 0.9 // max camera distance after a double click on a part

// ------------------------------------------------------------------ loading (cached, no Suspense)

// Bump when a /api/preview/* file changes meaning or format: the backend lets the browser cache them for a day, and
// a stale copy breaks the preview (e.g. hair/<code>/cap.png went from color+alpha to alpha only).
const ASSETS_VERSION = '2'
const versioned = (url: string) => `${url}${url.includes('?') ? '&' : '?'}v=${ASSETS_VERSION}`

const cache = new Map<string, Promise<unknown>>()
const gltfLoader = new GLTFLoader()
const textureLoader = new THREE.TextureLoader()

// number of loads in progress, for the "Carregando…" badge
let pending = 0
const pendingListeners = new Set<() => void>()
const setPending = (delta: number) => {
  pending += delta
  pendingListeners.forEach((l) => l())
}
const subscribePending = (listener: () => void) => {
  pendingListeners.add(listener)
  return () => pendingListeners.delete(listener)
}

function cached<T>(url: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(url) as Promise<T> | undefined
  if (!p) {
    p = load()
    setPending(1)
    p.finally(() => setPending(-1)).catch(() => undefined)
    p.catch(() => cache.delete(url)) // allow a retry after a failure
    cache.set(url, p)
  }
  return p
}

/** True while some preview asset is loading, after a short delay (fast loads do not blink the badge). */
function useLoading(delayMs = 200) {
  const busy = useSyncExternalStore(subscribePending, () => pending > 0)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setShown(busy), busy ? delayMs : 0)
    return () => clearTimeout(timer)
  }, [busy, delayMs])
  return busy && shown
}

/** Geometries of a GLB by node name (a node name may repeat). */
function loadMeshes(url: string) {
  return cached(url, async () => {
    const gltf = await gltfLoader.loadAsync(versioned(url))
    const out: Record<string, THREE.BufferGeometry[]> = {}
    gltf.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      // hair coeff is sampled with the second UV set; meshes that have only one reuse it
      const geometry = mesh.geometry
      if (!geometry.attributes.uv1 && geometry.attributes.uv) geometry.setAttribute('uv1', geometry.attributes.uv)
      out[o.name] = [...(out[o.name] ?? []), geometry]
    })
    return out
  })
}

/** color = false for data textures (masks, opacity); channel = UV set the texture is sampled with; repeat = UVs
 * outside 0..1 wrap around (scanned faces map the right eye at u -2..-1; clamped, it showed only the white). */
function loadTexture(url: string, color = true, channel = 0, repeat = false) {
  return cached(url, async () => {
    const texture = await textureLoader.loadAsync(versioned(url))
    if (repeat) texture.wrapS = texture.wrapT = THREE.RepeatWrapping
    // RX3 UVs follow the DirectX convention (origin at the top left), like glTF
    texture.flipY = false
    texture.channel = channel
    texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace // masks are data, not colors
    texture.anisotropy = 4
    return texture
  })
}

/** Value of load() for key; keeps returning the previous value while a new key loads. */
function useLoaded<T>(key: string | null, load: () => Promise<T>): T | undefined {
  const [state, setState] = useState<{ key: string; value: T }>()
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })
  useEffect(() => {
    if (key === null) return
    let alive = true
    loadRef.current().then(
      (value) => alive && setState({ key, value }),
      () => undefined, // missing asset: keep what is on screen
    )
    return () => {
      alive = false
    }
  }, [key])
  return key === null ? undefined : state?.value
}

// ------------------------------------------------------------------ parts

function HeadMesh({ glb, face, eyes }: { glb: string; face: string; eyes: string }) {
  const loaded = useLoaded([glb, face, eyes].join('|'), () => Promise.all([loadMeshes(glb), loadTexture(face), loadTexture(eyes, true, 0, true)]))
  if (!loaded) return null
  const [meshes, faceMap, eyesMap] = loaded
  return (
    <group>
      {meshes.head?.map((g, i) => (
        <mesh key={`head${i}`} geometry={g}>
          <meshStandardMaterial map={faceMap} roughness={0.75} metalness={0} />
        </mesh>
      ))}
      {meshes.eyes?.map((g, i) => (
        <mesh key={`eyes${i}`} geometry={g}>
          <meshStandardMaterial map={eyesMap} roughness={0.25} metalness={0} />
        </mesh>
      ))}
    </group>
  )
}

function Head({ a }: { a: PreviewAppearance }) {
  const faceQuery = new URLSearchParams({
    headtypecode: String(a.headtypecode),
    eyebrowcode: String(a.eyebrowcode),
    sideburnscode: String(a.sideburnscode),
    facialhaircolorcode: String(a.facialhaircolorcode),
    facialhairtypecode: String(a.facialhairtypecode),
    skintypecode: String(a.skintypecode),
    skintonecode: String(a.skintonecode),
  })
  return <HeadMesh glb={`/api/preview/head/${a.headtypecode}.glb`} face={`/api/preview/face.png?${faceQuery}`} eyes={`/api/preview/eyes/${a.eyecolorcode}.png`} />
}

function ScannedHead({ face, distance }: { face: PreviewScannedFace; distance: Distance }) {
  const file = (name: string) => `/api/preview/scanned/${name}?${face.query}`
  return <HeadMesh glb={distance === 'far' ? '/api/preview/lodhead.glb' : file('head.glb')} face={file('face.png')} eyes={file('eyes.png')} />
}

interface HairUrls {
  glb: string
  color: string
  cap: string
  strands: string
}

function Hair({ code, hairColor }: { code: number; hairColor: string }) {
  const base = `/api/preview/hair/${code}`
  const urls = code > 0 ? { glb: `${base}.glb`, color: `${base}/color.png`, cap: `${base}/cap.png`, strands: `${base}/strands.png` } : null
  return <HairMesh urls={urls} hairColor={hairColor} />
}

function ScannedHair({ face, distance }: { face: PreviewScannedFace; distance: Distance }) {
  const file = (name: string) => `/api/preview/scanned/${name}?${face.query}`
  const urls = { glb: file(distance === 'far' ? 'hairlod.glb' : 'hair.glb'), color: file('hair.png'), cap: file('cap.png'), strands: file('strands.png') }
  return <HairMesh urls={urls} hairColor={SCANNED_HAIR_COLOR} />
}

function HairMesh({ urls, hairColor }: { urls: HairUrls | null; hairColor: string }) {
  // hair_cm (tiling grey hair) uses the first UV set; the opacity (hair_coeff) the second one, for the cap too (the game
  // showed the front hair of faces like 71654 only that way; for generic caps both sets give the same)
  const loaded = useLoaded(urls ? [urls.glb, urls.color, urls.cap, urls.strands].join('|') : null, () =>
    Promise.all([loadMeshes(urls!.glb), loadTexture(urls!.color), loadTexture(urls!.cap, false, 1), loadTexture(urls!.strands, false, 1)]),
  )
  const color = useMemo(() => new THREE.Color(hairColor).multiplyScalar(HAIR_TINT_GAIN), [hairColor])
  if (!loaded) return null
  const [meshes, hairMap, cap, strands] = loaded
  const parts = [
    ['cap', cap],
    ['strands', strands],
  ] as const
  return (
    <group>
      {parts.flatMap(([part, map]) =>
        (meshes[part] ?? []).map((g, i) => (
          <mesh key={`${part}${i}`} geometry={g} renderOrder={part === 'cap' ? 1 : 2}>
            {/* matte (no specular sheen) and alpha-to-coverage instead of blending: no sorting artifacts between
                overlapping locks, edges smoothed by the canvas antialiasing */}
            <meshLambertMaterial
              map={hairMap}
              alphaMap={map}
              color={color}
              alphaToCoverage
              alphaTest={0.05}
              side={part === 'cap' ? THREE.FrontSide : THREE.DoubleSide}
            />
          </mesh>
        )),
      )}
    </group>
  )
}

function BodyPart({ part, code, texture, roughness, collar = 0 }: { part: string; code: number; texture: string; roughness: number; collar?: number }) {
  const glb = `/api/preview/body/${part}/${code}.glb${collar ? `?collar=${collar}` : ''}`
  const loaded = useLoaded(`${glb}|${texture}`, () => Promise.all([loadMeshes(glb), loadTexture(texture)]))
  if (!loaded) return null
  const [meshes, map] = loaded
  return (
    <group>
      {(meshes[part] ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={map} roughness={roughness} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

const srgb = (c: RGB) => new THREE.Color().setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace)

/** Street piece material: the texture is a mask (red/green/blue = primary/secondary/tertiary, alpha = shading)
 * painted with the 3 colors in the shader, so a color change needs no reload. */
function useMaskMaterial(map: THREE.Texture | undefined, colors: [RGB, RGB, RGB]) {
  const uniforms = useMemo(() => ({ uPri: { value: new THREE.Color() }, uSec: { value: new THREE.Color() }, uTer: { value: new THREE.Color() } }), [])
  const material = useMemo(() => {
    if (!map) return undefined
    // polygon offset: clothes win small overlaps with the reference-pose body underneath
    const m = new THREE.MeshStandardMaterial({ map, roughness: 0.85, metalness: 0, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -4 })
    m.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms)
      shader.fragmentShader = shader.fragmentShader
        .replace('void main() {', 'uniform vec3 uPri;\nuniform vec3 uSec;\nuniform vec3 uTer;\nvoid main() {')
        .replace(
          '#include <map_fragment>',
          'vec4 maskTexel = texture2D( map, vMapUv );\n' +
            'diffuseColor.rgb *= ( uPri * maskTexel.r + uSec * maskTexel.g + uTer * maskTexel.b ) * maskTexel.a;',
        )
    }
    return m
  }, [map, uniforms])
  useEffect(() => () => material?.dispose(), [material])
  useEffect(() => {
    uniforms.uPri.value.copy(srgb(colors[0]))
    uniforms.uSec.value.copy(srgb(colors[1]))
    uniforms.uTer.value.copy(srgb(colors[2]))
  })
  return material
}

function StreetPart({ part, mesh, piece }: { part: 'top' | 'bottom' | 'socks'; mesh: string; piece: StreetPiece }) {
  const glb = `/api/preview/body/${mesh}/${piece.style}.glb`
  const texture = `/api/preview/street/${part}/${piece.style}/${piece.pattern}.png`
  const loaded = useLoaded(`${glb}|${texture}`, () => Promise.all([loadMeshes(glb), loadTexture(texture, false)]))
  const material = useMaskMaterial(loaded?.[1], piece.colors)
  if (!loaded || !material) return null
  return (
    <group>
      {(loaded[0][mesh] ?? []).map((g, i) => (
        <mesh key={i} geometry={g} material={material} />
      ))}
    </group>
  )
}

function Body({ a, outfit }: { a: PreviewAppearance; outfit: PreviewOutfit }) {
  const skin = `/api/preview/skin/${a.skintonecode}.png`
  let clothes
  if (outfit.kind === 'team') {
    const shorts = kitTextureUrl('shorts', outfit.kit)
    clothes = (
      <>
        <BodyPart part="jersey" code={a.jerseysleevelengthcode} texture={kitTextureUrl('jersey', outfit.kit)} roughness={0.85} collar={outfit.kit.real?.collar} />
        <BodyPart part="arms" code={a.jerseysleevelengthcode} texture={skin} roughness={0.7} />
        <BodyPart part="shorts" code={0} texture={shorts} roughness={0.85} />
        <BodyPart part="socks" code={a.socklengthcode} texture={shorts} roughness={0.9} />
        <BodyPart part="legs" code={a.socklengthcode} texture={skin} roughness={0.7} />
      </>
    )
  } else {
    clothes = (
      <>
        <StreetPart part="top" mesh="top" piece={outfit.top} />
        <BodyPart part="arms" code={outfit.arms} texture={skin} roughness={0.7} />
        <StreetPart part="bottom" mesh="bottom" piece={outfit.bottom} />
        {/* trousers cover legs and socks (the reference-pose legs would poke through at the knees) */}
        {!outfit.fullLength && (
          <>
            <StreetPart part="socks" mesh="streetsocks" piece={outfit.socks} />
            {/* player.lua: leglength = socklength % 10 */}
            <BodyPart part="legs" code={outfit.socks.style % 10} texture={skin} roughness={0.7} />
          </>
        )}
      </>
    )
  }
  return (
    <group>
      {clothes}
      <BodyPart part="shoes" code={a.shoetypecode} texture={`/api/preview/shoe/${a.shoetypecode}.png`} roughness={0.5} />
      {/* every player can play in goal, so the gloves are always shown */}
      <BodyPart part="gloves" code={0} texture={`/api/preview/glove/${a.gkglovetypecode}.png`} roughness={0.6} />
    </group>
  )
}

// ------------------------------------------------------------------ camera

interface CameraGoal {
  camera: THREE.Vector3
  target: THREE.Vector3
}

/** Smoothly moves the camera to a goal (a view preset or a focused point); a user drag cancels it. */
function CameraRig({ goal }: { goal: CameraGoal | null }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  const active = useRef<CameraGoal | null>(null)
  useEffect(() => {
    active.current = goal
  }, [goal])
  useEffect(() => {
    if (!controls) return
    const stop = () => (active.current = null)
    controls.addEventListener('start', stop)
    return () => controls.removeEventListener('start', stop)
  }, [controls])
  useFrame((_, delta) => {
    const g = active.current
    if (!g || !controls) return
    const t = 1 - Math.exp(-delta * 10)
    camera.position.lerp(g.camera, t)
    controls.target.lerp(g.target, t)
    controls.update()
    if (camera.position.distanceTo(g.camera) < 0.002 && controls.target.distanceTo(g.target) < 0.002) active.current = null
  })
  return null
}

/** Double click on the model: orbit around the clicked point, a little closer (same viewing direction). */
function useFocus(setGoal: (g: CameraGoal) => void) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null
  return (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (!controls) return
    const offset = camera.position.clone().sub(controls.target)
    offset.setLength(Math.min(offset.length(), FOCUS_DISTANCE))
    setGoal({ camera: e.point.clone().add(offset), target: e.point.clone() })
  }
}

interface SceneProps {
  appearance: PreviewAppearance
  outfit: PreviewOutfit
  face?: PreviewScannedFace | null
  distance: Distance
  goal: CameraGoal | null
  setGoal: (g: CameraGoal) => void
  initialView: View
  initialScale: number
}

function Scene({ appearance, outfit, face, distance, goal, setGoal, initialView, initialScale }: SceneProps) {
  const focus = useFocus(setGoal)
  return (
    <>
      {/* no tone mapping (Canvas flat): the game's textures already carry their shading; ACES made it too dark */}
      {/* calibrated against in-game prints (20/10): a front-lit cheek renders close to its texture color */}
      <hemisphereLight args={['#ffffff', '#6a6058', 1.6]} />
      <directionalLight position={[0.6, 2.4, 1.6]} intensity={2.0} />
      <directionalLight position={[-0.9, 1.8, 0.8]} intensity={0.8} />
      <directionalLight position={[0, 2, -1.5]} intensity={0.8} />
      <group onDoubleClick={focus} scale={appearance.height / MODEL_HEIGHT_CM}>
        {face ? (
          <>
            <ScannedHead face={face} distance={distance} />
            <ScannedHair face={face} distance={distance} />
          </>
        ) : (
          <>
            <Head a={appearance} />
            <Hair code={appearance.hairtypecode} hairColor={appearance.hairColor} />
          </>
        )}
        {/* also in the face view: the collar hides the cut at the bottom of the neck */}
        <Body a={appearance} outfit={outfit} />
      </group>
      <OrbitControls makeDefault target={presetGoal(initialView, initialScale).target} minDistance={0.25} maxDistance={6} />
      <CameraRig goal={goal} />
    </>
  )
}

function presetGoal(view: View, scale: number): CameraGoal {
  const s = view === 'face' ? scale : 1
  const [cx, cy, cz] = VIEWS[view].camera
  const [tx, ty, tz] = VIEWS[view].target
  return { camera: new THREE.Vector3(cx, cy * s, cz), target: new THREE.Vector3(tx, ty * s, tz) }
}

export default function PlayerPreview({
  appearance,
  outfit,
  face,
  initialView = 'face',
  closeUpOnly = false,
}: {
  appearance: PreviewAppearance
  outfit: PreviewOutfit
  face?: PreviewScannedFace | null
  initialView?: View
  /** the game always draws the close-up head (game patch close_up_heads): no near/far choice */
  closeUpOnly?: boolean
}) {
  const { t } = useI18n()
  const [view, setView] = useState<View>(initialView)
  const [chosenDistance, setDistance] = useState<Distance>('near')
  const distance: Distance = closeUpOnly ? 'near' : chosenDistance
  const [goal, setGoal] = useState<CameraGoal | null>(null)
  const scale = appearance.height / MODEL_HEIGHT_CM
  const [initialScale] = useState(scale)
  const choose = (v: View) => {
    setView(v)
    setGoal(presetGoal(v, scale))
  }
  // the face view keeps the head framed when the height changes
  const [lastScale, setLastScale] = useState(scale)
  if (scale !== lastScale) {
    setLastScale(scale)
    if (view === 'face') setGoal(presetGoal('face', scale))
  }
  const loading = useLoading()
  return (
    <div className="relative size-full">
      <div className={cn('size-full', view === 'face' && '[mask-image:linear-gradient(to_bottom,black_80%,transparent)]')}>
        <Canvas flat camera={{ position: presetGoal(initialView, initialScale).camera.toArray(), fov: 30, near: 0.05, far: 20 }} dpr={[1, 2]}>
          <Scene appearance={appearance} outfit={outfit} face={face} distance={distance} goal={goal} setGoal={setGoal} initialView={initialView} initialScale={initialScale} />
        </Canvas>
      </div>
      <div className="absolute top-2 right-2 flex rounded-md border bg-background/80 p-0.5 text-xs backdrop-blur">
        {(['face', 'body'] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => choose(v)}
            className={cn('rounded px-2 py-0.5', view === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
          >
            {v === 'face' ? t('preview.face') : t('preview.body')}
          </button>
        ))}
      </div>
      {loading && (
        <div className="pointer-events-none absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-md border bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur">
          <LoaderCircle className="size-3.5 animate-spin" /> {t('common.loading')}
        </div>
      )}
      {face && !closeUpOnly && (
        <div className="absolute top-2 left-2 flex rounded-md border bg-background/80 p-0.5 text-xs backdrop-blur">
          {(['near', 'far'] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDistance(d)}
              title={d === 'near' ? t('preview.nearHint') : t('preview.farHint')}
              className={cn('rounded px-2 py-0.5', distance === d ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
            >
              {d === 'near' ? t('preview.near') : t('preview.far')}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
