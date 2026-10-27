import { Loader2, Trash2, Upload, User } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api, originalPhotoUrl, photoPreviewUrl } from '@/api/client'
import type { OriginalPlayer, Player } from '@/api/types'
import { FieldIssues } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useIssues, useProject } from '@/state/project'

/** Small round photo for lists (silhouette when the player has none). */
export function PlayerAvatar({ player, className }: { player: Player; className?: string }) {
  return <Avatar src={player.photo ? photoPreviewUrl(player.photo) : undefined} className={className} />
}

/** Same, for a player of the original game (its menu photo, read from the originals). */
export function OriginalPlayerAvatar({ player, className }: { player: OriginalPlayer; className?: string }) {
  return <Avatar src={player.photo ? originalPhotoUrl(player.id) : undefined} className={className} />
}

function Avatar({ src, className }: { src?: string; className?: string }) {
  return (
    <span className={cn('inline-flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted', className)}>
      {src ? (
        <img src={src} alt="" loading="lazy" className="size-full object-cover" />
      ) : (
        <User className="size-4 text-muted-foreground" />
      )}
    </span>
  )
}

/** Upload + preview of the menu photo (2D head) of a new player. */
export function PhotoCard({ player }: { player: Player }) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const issues = useIssues(player.uid, 'photo')

  const upload = async (file: File) => {
    setUploading(true)
    try {
      const r = await api.uploadImage(file)
      updatePlayer(player.uid, { photo: r.path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('image.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>{t('photo.title')}</CardTitle>
        <CardDescription>{t('photo.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="mx-auto flex size-40 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-[repeating-conic-gradient(var(--muted)_0_25%,transparent_0_50%)] bg-[length:16px_16px]"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            const f = e.dataTransfer.files[0]
            if (f) void upload(f)
          }}
          title={t('image.clickOrDrop')}
        >
          {uploading ? (
            <Loader2 className="animate-spin" />
          ) : player.photo ? (
            <img src={photoPreviewUrl(player.photo)} alt={t('photo.title')} className="size-full object-contain [image-rendering:pixelated]" />
          ) : (
            <span className="flex flex-col items-center gap-2 p-2 text-center text-xs text-muted-foreground">
              <Upload /> {t('image.clickOrDrop')}
            </span>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) void upload(f)
            e.target.value = ''
          }}
        />
        {player.photo && (
          <>
            <p className="text-center text-xs text-muted-foreground">{t('photo.previewSize')}</p>
            <Button variant="ghost" size="sm" className="w-full" onClick={() => updatePlayer(player.uid, { photo: undefined })}>
              <Trash2 /> {t('photo.remove')}
            </Button>
          </>
        )}
        <FieldIssues issues={issues} />
      </CardContent>
    </Card>
  )
}
