import { useState } from 'react'
import { API_BASE } from '../../lib/api'
import type { ScanResult } from '../../lib/types'

interface Props {
  result: ScanResult
  file?: File | null
}

export function ProofTab({ result, file }: Props) {
  const [downloading, setDownloading] = useState(false)

  async function downloadTrustReport() {
    if (!file) return
    setDownloading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API_BASE}/trust-report`, { method: 'POST', body: form })
      if (!res.ok) throw new Error('Failed to generate report')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `trust-report-${result.filename}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Could not generate Trust Report. Please try again.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">Audit summary</h3>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-gray-500">File</dt>
            <dd className="font-medium">{result.filename}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Risk level</dt>
            <dd className={`font-semibold ${
              result.risk_level === 'GREEN' ? 'text-green-700'
              : result.risk_level === 'ORANGE' ? 'text-orange-600'
              : 'text-red-700'
            }`}>{result.risk_level} ({result.risk_score}/100)</dd>
          </div>
          <div>
            <dt className="text-gray-500">Hidden instructions</dt>
            <dd className="font-medium">{result.prompt_injection_findings.length}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Personal data items</dt>
            <dd className="font-medium">{result.pii_findings.length}</dd>
          </div>
          <div>
            <dt className="text-gray-500">AI-generated text</dt>
            <dd className="font-medium capitalize">{result.ai_text_likelihood.toLowerCase()}</dd>
          </div>
        </dl>
      </div>

      <button
        type="button"
        disabled={downloading || !file}
        onClick={downloadTrustReport}
        className="flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-gray-700 disabled:opacity-50"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        {downloading ? 'Generating…' : 'Download Trust Report PDF'}
      </button>

      {!file && (
        <p className="text-xs text-amber-700">
          Re-upload this CV to generate its Trust Report PDF.
        </p>
      )}

      <p className="text-xs text-gray-400">
        This report is your candidate intelligence record. Claims flagged should be confirmed
        directly with the candidate. ProofHire Shield does not store CV data — all processing
        is ephemeral.
      </p>
    </div>
  )
}
