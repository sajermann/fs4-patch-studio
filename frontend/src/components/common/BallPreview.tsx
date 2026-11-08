import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { LoaderCircle } from 'lucide-react'
import * as THREE from 'three'
import { ballPreviewUrls, gameBallPreviewUrls } from '@/api/client'
import { useI18n } from '@/i18n'
import { loadMeshes, loadTexture, useLoaded, useLoading } from './PlayerPreview'

// 3D preview of one ball: one of the game's balls, or the user's pack ball converted by the backend exactly as the
// build converts it.

export type BallSource = { kind: 'game'; id: number } | { kind: 'project'; mesh: string; texture: string }

function urls(source: BallSource) {
  return source.kind === 'game' ? gameBallPreviewUrls(source.id) : ballPreviewUrls(source.mesh, source.texture)
}

function Ball({ source }: { source: BallSource }) {
  const { glb, texture } = urls(source)
  const loaded = useLoaded(`${glb}|${texture}`, () => Promise.all([loadMeshes(glb), loadTexture(texture)]))
  if (!loaded) return null
  const [meshes, map] = loaded
  return (
    <group>
      {(meshes.ball ?? []).map((g, i) => (
        <mesh key={i} geometry={g}>
          <meshStandardMaterial map={map} roughness={0.45} metalness={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

export default function BallPreview({ source }: { source: BallSource | null }) {
  const { t } = useI18n()
  const loading = useLoading()
  return (
    <div className="relative size-full">
      <Canvas flat camera={{ position: [0.25, 0.12, 0.42], fov: 30, near: 0.01, far: 10 }} dpr={[1, 2]}>
        <hemisphereLight args={['#ffffff', '#6a6058', 1.6]} />
        <directionalLight position={[0.6, 2.4, 1.6]} intensity={2.0} />
        <directionalLight position={[-0.9, 1.8, 0.8]} intensity={0.8} />
        <directionalLight position={[0, 2, -1.5]} intensity={0.8} />
        {source && <Ball source={source} />}
        <OrbitControls makeDefault target={[0, 0, 0]} minDistance={0.18} maxDistance={1.5} />
      </Canvas>
      {loading && (
        <div className="pointer-events-none absolute top-2 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-md border bg-background/80 px-2 py-1 text-xs text-muted-foreground backdrop-blur">
          <LoaderCircle className="size-3.5 animate-spin" /> {t('common.loading')}
        </div>
      )}
      {!source && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-muted-foreground">
          {t('balls.previewNeedsFiles')}
        </div>
      )}
    </div>
  )
}
