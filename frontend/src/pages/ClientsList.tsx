import { useEffect, useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { createClient, deleteClient, listClients } from '../lib/api'
import type { Client } from '../lib/types'

function ClientsInner() {
  const { getToken } = useAuth()
  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to manage clients.')
        return
      }
      setClients((await listClients(token)).clients)
    } catch (e) {
      setError((e as Error).message || 'Could not load clients.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      await createClient(
        {
          name: name.trim(),
          contact_name: contact.trim() || undefined,
          contact_email: email.trim() || undefined,
        },
        token,
      )
      setName('')
      setContact('')
      setEmail('')
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    const token = await getToken()
    if (!token) return
    await deleteClient(id, token)
    await refresh()
  }

  const field =
    'rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none'

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Clients</h2>
        <p className="text-sm text-gray-500">The companies you fill roles for.</p>
      </div>

      <form
        onSubmit={add}
        className="flex flex-wrap items-end gap-2 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Client name *" className={`${field} grow`} />
        <input value={contact} onChange={(e) => setContact(e.target.value)} placeholder="Contact name" className={field} />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Contact email" className={field} />
        <button
          type="submit"
          disabled={!name.trim() || busy}
          className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-50"
        >
          Add client
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-sm text-gray-400">Loading…</div>
      ) : clients.length === 0 ? (
        <p className="py-10 text-center text-sm text-gray-400">No clients yet.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-100 bg-gray-50/60 text-xs uppercase tracking-wide text-gray-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Name</th>
                <th className="px-4 py-3 font-semibold">Contact</th>
                <th className="px-4 py-3 font-semibold">Email</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {clients.map((c) => (
                <tr key={c.id} className="hover:bg-blue-50/40">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                  <td className="px-4 py-3 text-gray-500">{c.contact_name ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{c.contact_email ?? '—'}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => void remove(c.id)}
                      className="text-gray-300 transition hover:text-red-500"
                      title="Delete client"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function ClientsList() {
  return (
    <>
      <SignedIn>
        <ClientsInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to manage clients</p>
          <SignInButton mode="modal">
            <button className="mt-4 rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white shadow-sm">
              Sign in
            </button>
          </SignInButton>
        </div>
      </SignedOut>
    </>
  )
}
