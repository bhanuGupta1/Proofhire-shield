import { ClerkProvider } from '@clerk/clerk-react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ScanPage } from './pages/ScanPage'
import { CandidatesList } from './pages/CandidatesList'
import { CandidateDetail } from './pages/CandidateDetail'
import { JobsList } from './pages/JobsList'
import { JobDetail } from './pages/JobDetail'
import { JobForm } from './pages/JobForm'

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined

export default function App() {
  if (!CLERK_KEY) {
    // Clerk not configured — render a clear error so the operator notices,
    // rather than silently shipping a build without history/candidate storage.
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <div className="max-w-md rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
          <p className="font-semibold mb-2">Authentication is not configured.</p>
          <p>
            Set <code className="font-mono">VITE_CLERK_PUBLISHABLE_KEY</code> in the
            build environment and redeploy.
          </p>
        </div>
      </div>
    )
  }
  return (
    <ClerkProvider publishableKey={CLERK_KEY}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<ScanPage />} />
            <Route path="candidates" element={<CandidatesList />} />
            <Route path="candidates/:id" element={<CandidateDetail />} />
            <Route path="jobs" element={<JobsList />} />
            <Route path="jobs/new" element={<JobForm />} />
            <Route path="jobs/:id" element={<JobDetail />} />
            <Route path="jobs/:id/edit" element={<JobForm />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ClerkProvider>
  )
}
