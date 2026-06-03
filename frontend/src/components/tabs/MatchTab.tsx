import type { ScanResult } from '../../lib/types'

interface Props {
  result: ScanResult
}

const TIER_COLOURS: Record<string, string> = {
  'Entry':             'bg-gray-100 text-gray-700',
  'Mid-level':         'bg-blue-100 text-blue-700',
  'Senior':            'bg-purple-100 text-purple-700',
  'Principal / Lead':  'bg-amber-100 text-amber-700',
}

const CATEGORY_COLOURS: Record<string, string> = {
  'Languages':              'bg-blue-50 text-blue-700 border-blue-200',
  'Frameworks & Libraries': 'bg-purple-50 text-purple-700 border-purple-200',
  'Cloud & DevOps':         'bg-orange-50 text-orange-700 border-orange-200',
  'Databases':              'bg-green-50 text-green-700 border-green-200',
  'Tools & Practices':      'bg-gray-50 text-gray-700 border-gray-200',
  'Testing & QA':           'bg-pink-50 text-pink-700 border-pink-200',
  'Data & ML Ops':          'bg-cyan-50 text-cyan-700 border-cyan-200',
}

export function MatchTab({ result }: Props) {
  const m = result.match_analysis
  const hasSkills = m.total_skills_found > 0
  const hasClaims = m.key_claims.length > 0

  return (
    <div className="space-y-6">
      {/* Recruiter one-liner — copy into ATS notes */}
      <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 font-mono text-sm text-gray-800">
        {m.summary}
      </div>

      {/* Phase 9 v4 — engine badge. Tells the recruiter which path
          actually produced the education / tier values on THIS scan, so
          they can sanity-check unexpected labels. "regex" also appears
          when the LLM was attempted but couldn't complete. */}
      {m.match_engine && (
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-gray-400">Analysed with</span>
          {m.match_engine === 'llm' ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 font-semibold text-blue-700">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
              </svg>
              AI engine
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-semibold text-gray-600">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z"/>
              </svg>
              Fast engine
            </span>
          )}
        </div>
      )}

      {/* CV completeness meter */}
      <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-500">CV completeness</span>
          <span
            className={`font-semibold ${
              m.completeness.score >= 70
                ? 'text-green-600'
                : m.completeness.score >= 40
                ? 'text-amber-600'
                : 'text-red-600'
            }`}
          >
            {m.completeness.score}%
          </span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className={`h-full ${
              m.completeness.score >= 70
                ? 'bg-green-500'
                : m.completeness.score >= 40
                ? 'bg-amber-500'
                : 'bg-red-500'
            }`}
            style={{ width: `${m.completeness.score}%` }}
          />
        </div>
        {Object.entries(m.completeness.breakdown).filter(([, hit]) => !hit).length > 0 && (
          <p className="mt-2 text-xs text-gray-400">
            Missing:{' '}
            {Object.entries(m.completeness.breakdown)
              .filter(([, hit]) => !hit)
              .map(([label]) => label)
              .join(', ')}
          </p>
        )}
      </div>

      {/* Summary bar */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Experience</span>
          <span className={`rounded-full px-3 py-1 text-sm font-semibold ${TIER_COLOURS[m.experience_tier] ?? 'bg-gray-100 text-gray-700'}`}>
            {m.experience_tier}
            {m.years_experience !== null && ` · ${m.years_experience}y`}
          </span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Education</span>
          <span className="text-sm font-medium text-gray-800">{m.education_level}</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Skills found</span>
          <span className="text-sm font-semibold text-gray-800">{m.total_skills_found}</span>
        </div>
      </div>

      {/* Skills by category */}
      {hasSkills ? (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="mb-4 text-sm font-semibold text-gray-800">Skills detected</h3>
          <div className="space-y-3">
            {Object.entries(m.skills).map(([category, skills]) => (
              <div key={category}>
                <p className="mb-2 text-xs font-medium text-gray-400 uppercase tracking-wide">{category}</p>
                <div className="flex flex-wrap gap-2">
                  {skills.map((skill) => (
                    <span
                      key={skill}
                      className={`rounded-md border px-2.5 py-1 text-xs font-medium ${CATEGORY_COLOURS[category] ?? 'bg-gray-50 text-gray-600 border-gray-200'}`}
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-200 bg-white p-5 text-center">
          <p className="text-sm text-gray-400">No recognised technical skills detected in this CV.</p>
        </div>
      )}

      {/* Interview probes */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold text-gray-800">Interview probes</h3>
        <p className="mb-3 text-xs text-gray-400">Based on skills and experience tier — use to verify competency claims.</p>
        <ol className="space-y-3">
          {m.interview_probes.map((probe, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {i + 1}
              </span>
              <span className="text-sm text-gray-700">{probe}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* Key claims to verify */}
      {hasClaims && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
          <h3 className="mb-3 text-sm font-semibold text-amber-800">Claims to verify</h3>
          <p className="mb-3 text-xs text-amber-600">These statements contain specific, verifiable assertions.</p>
          <ul className="space-y-2">
            {m.key_claims.map((claim, i) => (
              <li key={i} className="flex gap-2 text-sm text-amber-800">
                <span className="mt-0.5 shrink-0 text-amber-500">&rsaquo;</span>
                <span>&ldquo;{claim}&rdquo;</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Red flags */}
      {m.red_flags && m.red_flags.length > 0 && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-5">
          <h3 className="mb-3 text-sm font-semibold text-rose-800">
            Red flags — verify before advancing
          </h3>
          <ul className="space-y-2">
            {m.red_flags.map((flag, i) => (
              <li key={i} className="flex gap-2 text-sm text-rose-800">
                <span className="mt-0.5 shrink-0">⚠</span>
                <span>{flag}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-rose-500">
            Heuristic signals only — not a hiring decision.
          </p>
        </div>
      )}

      <p className="text-xs text-gray-400">
        Skills extracted automatically from CV text using keyword matching.
        Verify all claims directly with the candidate.
      </p>
    </div>
  )
}
