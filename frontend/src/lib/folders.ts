/** Folder lists as they are saved in the settings: trimmed, without empty rows. */
export const cleanFolders = (folders: string[]) => folders.map((f) => f.trim()).filter(Boolean)
