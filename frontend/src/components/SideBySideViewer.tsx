interface Props {
  original: string
  safeCopy: string
}

function TextPane({ label, text, highlight }: { label: string; text: string; highlight?: boolean }) {
  const lines = text.split('\n')
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide ${highlight ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-500'}`}>
        {label}
      </div>
      <div className="overflow-y-auto p-4 text-sm leading-relaxed font-mono max-h-96 whitespace-pre-wrap">
        {lines.map((line, i) => {
          const isRemoved = line.includes('[HIDDEN INSTRUCTION REMOVED]')
          const isPII = line.includes('[PII:')
          return (
            <span
              key={i}
              className={
                isRemoved
                  ? 'block bg-red-100 text-red-700 rounded px-1 my-0.5'
                  : isPII
                  ? 'block bg-yellow-50 text-yellow-800'
                  : 'block'
              }
            >
              {line || ' '}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export function SideBySideViewer({ original, safeCopy }: Props) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <TextPane label="Original CV" text={original} />
      <TextPane label="Safe copy" text={safeCopy} highlight />
    </div>
  )
}
