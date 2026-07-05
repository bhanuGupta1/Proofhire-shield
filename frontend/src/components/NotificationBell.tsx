import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../lib/api'
import type { Notification } from '../lib/types'

export function NotificationBell() {
  const { getToken } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<Notification[]>([])
  const ref = useRef<HTMLDivElement>(null)

  async function refreshCount() {
    try {
      const token = await getToken()
      if (!token) return
      setUnread(await getUnreadCount(token))
    } catch {
      // Degrade quietly — the bell just shows no badge.
    }
  }

  useEffect(() => {
    void refreshCount()
    // Poll every 60s so the badge stays roughly current without a socket.
    const t = window.setInterval(() => void refreshCount(), 60_000)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Close on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next) {
      const token = await getToken()
      if (!token) return
      const list = await listNotifications(token)
      setItems(list.notifications)
      setUnread(list.unread_count)
    }
  }

  async function openItem(n: Notification) {
    const token = await getToken()
    if (token && !n.read) {
      await markNotificationRead(n.id, token)
      setUnread((u) => Math.max(0, u - 1))
      setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)))
    }
    setOpen(false)
    if (n.candidate_id) navigate(`/candidates/${n.candidate_id}`)
  }

  async function readAll() {
    const token = await getToken()
    if (!token) return
    await markAllNotificationsRead(token)
    setUnread(0)
    setItems((xs) => xs.map((x) => ({ ...x, read: true })))
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => void toggle()}
        className="relative rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700"
        title="Notifications"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
            <span className="text-sm font-semibold text-gray-700">Notifications</span>
            {items.some((i) => !i.read) && (
              <button
                onClick={() => void readAll()}
                className="text-xs font-medium text-blue-600 hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-xs text-gray-400">
                You're all caught up.
              </p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => void openItem(n)}
                  className={`block w-full border-b border-gray-50 px-4 py-3 text-left transition hover:bg-gray-50 ${
                    n.read ? 'opacity-60' : ''
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {!n.read && (
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900">{n.title}</p>
                      {n.body && (
                        <p className="mt-0.5 text-xs leading-snug text-gray-500">{n.body}</p>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
