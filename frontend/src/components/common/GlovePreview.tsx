import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import * as THREE from 'three'
import { gameGlovePreviewUrl, glovePreviewUrl } from '@/api/client'
import { useI18n } from '@/i18n'
import { loadMeshes, loadTexture, useLoaded, useLoading } from './PlayerPreview'

// 3D preview of a goalkeeper glove on the right hand, as the game shows it: every glove uses the game's one glove
// mesh, only the color map changes (the user's glove: its pack file converted by the backend as the build does).

export type GloveSource = { kind: 'game'; code: number } | { kind: 'project'; texture: string }

const ARMS_CODE = 1 // arms_1: forearms and hands (long sleeves)
const SKIN_TONE = 4
const MESH = '/api/preview/body/gloves/0.glb'
const ARMS = `/api/preview/body/arms/${ARMS_CODE}.glb`
const SKIN = `/api/preview/skin/${SKIN_TONE}.png`
const HAND: [number, number, number] = [0.56, 1.18, 0.2] // the right glove in the reference pose (meters)

function Glove({ source }: { source: GloveSource }) {
  const texture = source.kind === 'game' ? gameGlovePreviewUrl(source.code) : glovePreviewUrl(source.texture)
  const loaded = useLoaded(`${MESH}|${texture}`, () => Promise.all([loadMeshes(MESH), loadTexture(texture)]))
  if (!loaded) return null
  const [meshes, map] = loaded
  return (
    <group>
      {(meshes.gloves ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={map} roughness={0.6} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

function Arms() {
  const loaded = useLoaded(`${ARMS}|${SKIN}`, () => Promise.all([loadMeshes(ARMS), loadTexture(SKIN)]))
  if (!loaded) return null
  const [meshes, map] = loaded
  return (
    <group>
      {(meshes.arms ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={map} roughness={0.7} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

export default function GlovePreview({ source }: { source: GloveSource | null }) {
  const { t } = useI18n()
  const loading = useLoading()
  return (
    <div className="relative size-full">
      <Canvas flat camera={{ position: [HAND[0] + 0.32, HAND[1] + 0.28, HAND[2] + 0.42], fov: 30, near: 0.02, far: 10 }} dpr={[1, 2]}>
        <hemisphereLight args={['#ffffff', '#6a6058', 1.6]} />
        <directionalLight position={[0.6, 2.4, 1.6]} intensity={2.0} />
        <directionalLight position={[-0.9, 1.8, 0.8]} intensity={0.8} />
        <directionalLight position={[0, 2, -1.5]} intensity={0.8} />
        <Arms />
        {source && <Glove source={source} />}
        <OrbitControls makeDefault target={HAND} minDistance={0.15} maxDistance={2.5} />
      </Canvas>
      {loading && (
        <div className="pointer-events-none absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-md border bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur">
          <LoaderCircle className="size-3.5 animate-spin" /> {t('common.loading')}
        </div>
      )}
      {!source && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-muted-foreground">
          {t('gloves.previewNeedsFile')}
        </div>
      )}
    </div>
  )
}
