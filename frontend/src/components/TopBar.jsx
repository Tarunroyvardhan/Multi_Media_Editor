import React from 'react'
import { Link } from 'react-router-dom'
import { Sun, Moon } from 'lucide-react'
import { useAuth } from '../api/AuthContext'
import { useTheme } from '../theme'

export default function TopBar({ right }) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const initial = user?.email?.[0]?.toUpperCase() || '?'

  return (
    <div className="topbar">
      <Link to="/" className="brand">
        <span className="brand-mark" />
        Framewerk
      </Link>
      <div className="topbar-right">
        {right}
        <button
          className="btn-icon btn"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        {user && (
          <div className="user-chip">
            <div className="user-avatar">{initial}</div>
            <span>{user.email}</span>
          </div>
        )}
        {user && (
          <button className="btn btn-ghost" onClick={logout}>
            Log out
          </button>
        )}
      </div>
    </div>
  )
}