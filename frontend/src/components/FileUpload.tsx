import { useRef, useState } from 'react'

interface Props {
  onFile: (file: File) => void
  loading: boolean
}

const ACCEPTED = '.pdf,.docx,.txt'

export function FileUpload({ onFile, loading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    onFile(files[0])
  }

  return (
    <div
      className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-8 py-12 transition-colors
        ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white hover:border-gray-400'}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
    >
      <svg className="mb-4 h-10 w-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" />
      </svg>
      <p className="mb-1 text-base font-medium text-gray-700">Drop a CV here</p>
      <p className="mb-4 text-sm text-gray-500">PDF, DOCX, or TXT · max 10 MB</p>
      <button
        type="button"
        disabled={loading}
        onClick={() => inputRef.current?.click()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Scanning…' : 'Choose file'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  )
}
