import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../api/AuthContext'

export default function TopBar({ right }) {
  const { user, logout } = useAuth()
  const initial = user?.email?.[0]?.toUpperCase() || '?'

  return (
    <div className="topbar">
      <Link to="/" className="brand">
        <span className="brand-mark" />
        Framewerk
      </Link>
      <div className="topbar-right">
        {right}
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
