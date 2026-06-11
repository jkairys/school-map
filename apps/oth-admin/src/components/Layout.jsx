import { Outlet, NavLink } from 'react-router-dom'
import { LayoutDashboard } from 'lucide-react'

export default function Layout() {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      <header className="bg-white border-b border-neutral-200 px-6 py-3 flex items-center gap-4">
        <LayoutDashboard size={20} className="text-neutral-500" />
        <span className="font-semibold text-sm tracking-tight">OTH admin</span>
        <nav className="flex items-center gap-1 ml-4">
          <NavLink
            to="/areas"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-neutral-100 text-neutral-900'
                  : 'text-neutral-500 hover:text-neutral-800 hover:bg-neutral-50'
              }`
            }
          >
            Areas
          </NavLink>
        </nav>
      </header>
      <main className="px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
