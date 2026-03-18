import { useState, useRef, useCallback } from 'react'

const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const ACCEPTED_EXTENSIONS = '.png,.jpg,.jpeg,.webp'
const MAX_FILE_SIZE = 5 * 1024 * 1024 // 5MB
const MAX_IMAGES = 10

const ROLE_OPTIONS = [
  { value: 'targeted', label: 'Designer + Frontend' },
  { value: 'all', label: 'All Agents' },
]

function generateId() {
  return crypto.randomUUID().split('-')[0]
}

function createImageReference(file) {
  return {
    id: generateId(),
    file,
    filename: file.name,
    caption: '',
    targetRoles: ['designer', 'frontend'],
    preview: URL.createObjectURL(file),
  }
}

function validateFile(file) {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return `${file.name}: unsupported format. Use PNG, JPG, or WebP.`
  }
  if (file.size > MAX_FILE_SIZE) {
    return `${file.name}: exceeds 5MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB).`
  }
  return null
}

export default function ImageReferenceUpload({ images, onChange }) {
  const [collapsed, setCollapsed] = useState(true)
  const [dragOver, setDragOver] = useState(false)
  const [errors, setErrors] = useState([])
  const fileInputRef = useRef(null)

  const addFiles = useCallback((files) => {
    const newErrors = []
    const validRefs = []
    const remaining = MAX_IMAGES - images.length

    if (remaining <= 0) {
      newErrors.push(`Maximum ${MAX_IMAGES} images reached.`)
      setErrors(newErrors)
      return
    }

    const filesToProcess = Array.from(files).slice(0, remaining)
    if (files.length > remaining) {
      newErrors.push(`Only ${remaining} more image(s) allowed. ${files.length - remaining} skipped.`)
    }

    for (const file of filesToProcess) {
      const err = validateFile(file)
      if (err) {
        newErrors.push(err)
      } else {
        validRefs.push(createImageReference(file))
      }
    }

    setErrors(newErrors)
    if (validRefs.length > 0) {
      onChange([...images, ...validRefs])
    }
  }, [images, onChange])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    addFiles(e.dataTransfer.files)
  }, [addFiles])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
  }, [])

  const handleFileSelect = useCallback((e) => {
    if (e.target.files?.length) {
      addFiles(e.target.files)
    }
    // Reset so same file can be re-selected
    e.target.value = ''
  }, [addFiles])

  const removeImage = useCallback((id) => {
    const img = images.find((i) => i.id === id)
    if (img?.preview) URL.revokeObjectURL(img.preview)
    onChange(images.filter((i) => i.id !== id))
  }, [images, onChange])

  const updateCaption = useCallback((id, caption) => {
    onChange(images.map((i) => (i.id === id ? { ...i, caption } : i)))
  }, [images, onChange])

  const updateTargetRoles = useCallback((id, mode) => {
    const targetRoles = mode === 'all'
      ? ['designer', 'frontend', 'backend', 'qa', 'architect', 'product_owner']
      : ['designer', 'frontend']
    onChange(images.map((i) => (i.id === id ? { ...i, targetRoles } : i)))
  }, [images, onChange])

  const isAllRoles = (img) => img.targetRoles.length > 2

  return (
    <div className="space-y-2">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex items-center gap-2 w-full text-left bg-transparent border-0 cursor-pointer p-0 group"
        aria-expanded={!collapsed}
      >
        <span className="text-xs font-medium text-zinc-400 font-mono uppercase tracking-wider group-hover:text-crt-green transition-colors">
          Image References
        </span>
        {images.length > 0 && (
          <span
            className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full text-[10px] font-mono font-bold bg-crt-green/15 text-crt-green border border-crt-green/30"
            role="img"
            aria-label={`${images.length} image${images.length !== 1 ? 's' : ''} attached`}
          >
            {images.length}
          </span>
        )}
        <svg
          className={`w-3 h-3 text-zinc-500 transition-transform ${collapsed ? '' : 'rotate-180'}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="space-y-3 animate-fade-in">
          {/* Error messages */}
          {errors.length > 0 && (
            <div className="text-xs text-signal-red font-mono space-y-0.5" role="alert">
              {errors.map((err, i) => (
                <p key={i}>{err}</p>
              ))}
            </div>
          )}

          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                fileInputRef.current?.click()
              }
            }}
            aria-label="Drop images here or click to browse"
            className={`
              relative rounded border-2 border-dashed p-4 text-center cursor-pointer transition-all
              ${dragOver
                ? 'border-crt-green bg-crt-green/5'
                : 'border-retro-border hover:border-zinc-500 hover:bg-retro-grid/50'
              }
              ${images.length >= MAX_IMAGES ? 'opacity-50 pointer-events-none' : ''}
            `}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              multiple
              onChange={handleFileSelect}
              className="hidden"
              aria-hidden="true"
            />
            <div className="flex flex-col items-center gap-1.5">
              <svg className="w-6 h-6 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
              </svg>
              <p className="text-xs text-zinc-500 font-mono">
                {dragOver ? 'Drop images here' : 'Drop images or click to browse'}
              </p>
              <p className="text-[10px] text-zinc-600 font-mono">
                PNG, JPG, WebP — max 5MB each, {MAX_IMAGES - images.length} remaining
              </p>
            </div>
          </div>

          {/* Thumbnail grid */}
          {images.length > 0 && (
            <div className="grid grid-cols-3 gap-3">
              {images.map((img) => (
                <div
                  key={img.id}
                  className="relative rounded overflow-hidden border border-retro-border bg-retro-grid group"
                >
                  {/* Thumbnail */}
                  <div className="aspect-square overflow-hidden bg-black/20">
                    <img
                      src={img.preview}
                      alt={img.caption || img.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>

                  {/* Remove button */}
                  <button
                    type="button"
                    onClick={() => removeImage(img.id)}
                    className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/70 hover:bg-signal-red/80 text-zinc-300 hover:text-white flex items-center justify-center text-xs cursor-pointer transition-colors border-0 opacity-0 group-hover:opacity-100 focus:opacity-100"
                    aria-label={`Remove ${img.filename}`}
                  >
                    &times;
                  </button>

                  {/* Caption + role targeting */}
                  <div className="p-1.5 space-y-1">
                    <input
                      type="text"
                      value={img.caption}
                      onChange={(e) => updateCaption(img.id, e.target.value)}
                      placeholder="Caption..."
                      className="retro-input w-full rounded px-1.5 py-0.5 text-[10px]"
                      maxLength={120}
                      aria-label={`Caption for ${img.filename}`}
                    />
                    <select
                      value={isAllRoles(img) ? 'all' : 'targeted'}
                      onChange={(e) => updateTargetRoles(img.id, e.target.value)}
                      className="retro-input w-full rounded px-1 py-0.5 text-[10px] cursor-pointer"
                      aria-label={`Target roles for ${img.filename}`}
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
