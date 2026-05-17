'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { getUser, clearAuth, isAdmin, isTokenValid, type AuthUser } from '@/lib/auth'
import {
  LayoutDashboard, Users, TrendingUp, MessageSquare,
  UserCog, LogOut, Menu, X, GraduationCap, BarChart2, Settings,
} from 'lucide-react'
import ChatWidget from '@/components/ChatWidget'

const NAV_ITEMS = [
  { href: '/dashboard',   label: 'Dashboard',    icon: LayoutDashboard, adminOnly: false },
  { href: '/students',    label: 'Students',     icon: Users,           adminOnly: false },
  { href: '/risk',        label: 'Risk Analysis', icon: TrendingUp,     adminOnly: false },
  { href: '/analytics',   label: 'Analytics',    icon: BarChart2,       adminOnly: false },
  { href: '/supervisors', label: 'Supervisors',  icon: UserCog,         adminOnly: true  },
  { href: '/chat',        label: 'AI Assistant', icon: MessageSquare,   adminOnly: false },
  { href: '/admin',       label: 'Admin Panel',  icon: Settings,        adminOnly: true  },
]

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router   = useRouter()
  const pathname = usePathname()
  const [user, setUser]         = useState<AuthUser | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    const u = getUser()
    if (!u || !isTokenValid()) {
      clearAuth()
      router.replace('/login')
      return
    }
    setUser(u)
  }, [router])

  function handleLogout() {
    clearAuth()
    router.push('/login')
  }

  const visibleNav = NAV_ITEMS.filter(n => !n.adminOnly || isAdmin(user))

  if (!user) return null   // wait for auth check

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* ── Mobile overlay ── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      <aside className={`
        fixed inset-y-0 left-0 z-30 w-64 bg-indigo-900 text-white flex flex-col
        transform transition-transform duration-200
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:relative lg:translate-x-0 lg:flex
      `}>
        {/* Brand */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-indigo-800">
          <div className="w-9 h-9 bg-white/20 rounded-lg flex items-center justify-center">
            <GraduationCap className="w-5 h-5" />
          </div>
          <div>
            <p className="font-bold text-sm leading-tight">Postgraduate</p>
            <p className="text-indigo-300 text-xs mt-0.5">Monitoring System</p>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setSidebarOpen(false)}>
            <X className="w-5 h-5 text-indigo-300" />
          </button>
        </div>

        {/* Role badge */}
        <div className="px-6 py-3">
          <span className={`text-xs font-semibold px-2 py-1 rounded-full ${
            isAdmin(user)
              ? 'bg-amber-500/20 text-amber-300'
              : 'bg-indigo-500/20 text-indigo-300'
          }`}>
            {user.role}
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-1">
          {visibleNav.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + '/')
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-white/15 text-white'
                    : 'text-indigo-200 hover:bg-white/10 hover:text-white'
                }`}
              >
                <Icon className="w-4.5 h-4.5 w-[18px] h-[18px] flex-shrink-0" />
                {label}
              </Link>
            )
          })}
        </nav>

        {/* User / Logout */}
        <div className="px-4 py-4 border-t border-indigo-800">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-full flex items-center justify-center text-sm font-bold">
              {user.name.charAt(0)}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{user.name}</p>
              <p className="text-indigo-400 text-xs">{user.staff_id}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 text-indigo-300 hover:text-white hover:bg-white/10 rounded-lg text-sm transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar (mobile) */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b">
          <button onClick={() => setSidebarOpen(true)}>
            <Menu className="w-5 h-5 text-gray-600" />
          </button>
          <span className="font-semibold text-gray-800">PG Monitoring</span>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>

      {/* Floating AI chat widget — hidden on the dedicated /chat page */}
      {pathname !== '/chat' && <ChatWidget />}
    </div>
  )
}
