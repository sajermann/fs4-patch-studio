import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import * as THREE from 'three'
import { bootPreviewUrls } from '@/api/client'
import { useI18n } from '@/i18n'
import { loadMeshes, loadTexture, useLoaded, useLoading } from './PlayerPreview'

// 3D preview of one boot on the lower legs, as the game wears it: one of the game's boots, or the user's pack boot
// converted by the backend exactly as the build converts it (collar moved off the sock). The sock and the leg are the
// game's own meshes, so the fit at the collar shows.

export type BootSource = { kind: 'game'; code: number } | { kind: 'project'; mesh: string; texture: string }

const SOCK_CODE = 1 // socklengthcode of the sock shown (every sock has the same foot)
const SKIN_TONE = 4
const SOCK_COLOR = '#d9dde3'

function urls(source: BootSource) {
  return source.kind === 'game'
    ? { glb: `/api/preview/body/shoes/${source.code}.glb`, texture: `/api/preview/shoe/${source.code}.png` }
    : bootPreviewUrls(source.mesh, source.texture)
}

function Boot({ source }: { source: BootSource }) {
  const { glb, texture } = urls(source)
  const loaded = useLoaded(`${glb}|${texture}`, () => Promise.all([loadMeshes(glb), loadTexture(texture)]))
  if (!loaded) return null
  const [meshes, map] = loaded
  return (
    <group>
      {(meshes.shoes ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={map} roughness={0.5} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

function Legs() {
  const sock = `/api/preview/body/socks/${SOCK_CODE}.glb`
  const legs = `/api/preview/body/legs/${SOCK_CODE}.glb`
  const skin = `/api/preview/skin/${SKIN_TONE}.png`
  const loaded = useLoaded(`${sock}|${legs}|${skin}`, () => Promise.all([loadMeshes(sock), loadMeshes(legs), loadTexture(skin)]))
  if (!loaded) return null
  const [socks, leg, skinMap] = loaded
  return (
    <group>
      {(socks.socks ?? []).map((g, i) => (
        <mesh key={`s${i}`} geometry={g}>
          <meshStandardMaterial color={SOCK_COLOR} roughness={0.9} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
      {(leg.legs ?? []).map((g, i) => (
        <mesh key={`l${i}`} geometry={g}>
          <meshStandardMaterial map={skinMap} roughness={0.7} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

export default function BootPreview({ source }: { source: BootSource | null }) {
  const { t } = useI18n()
  const loading = useLoading()
  return (
    <div className="relative size-full">
      <Canvas flat camera={{ position: [0.62, 0.34, 0.62], fov: 30, near: 0.02, far: 10 }} dpr={[1, 2]}>
        <hemisphereLight args={['#ffffff', '#6a6058', 1.6]} />
        <directionalLight position={[0.6, 2.4, 1.6]} intensity={2.0} />
        <directionalLight position={[-0.9, 1.8, 0.8]} intensity={0.8} />
        <directionalLight position={[0, 2, -1.5]} intensity={0.8} />
        <Legs />
        {source && <Boot source={source} />}
        <OrbitControls makeDefault target={[0, 0.12, 0.04]} minDistance={0.2} maxDistance={2.5} />
      </Canvas>
      {loading && (
        <div className="pointer-events-none absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-md border bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur">
          <LoaderCircle className="size-3.5 animate-spin" /> {t('common.loading')}
        </div>
      )}
      {!source && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-muted-foreground">
          {t('boots.previewNeedsFiles')}
        </div>
      )}
    </div>
  )
}
