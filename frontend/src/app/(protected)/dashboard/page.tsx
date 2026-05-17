'use client'
import { useEffect, useState } from 'react'
import { Users, AlertTriangle, Clock, TrendingUp } from 'lucide-react'
import StatsCard from '@/components/StatsCard'
import RiskChart from '@/components/RiskChart'
import { getMySummary, getUpcomingDeadlines } from '@/lib/api'
import { getUser, isAdmin } from '@/lib/auth'

export default function DashboardPage() {
  const user = getUser()
  const [summary, setSummary]     = useState<any>(null)
  const [deadlines, setDeadlines] = useState<any[]>([])
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    Promise.all([getMySummary(), getUpcomingDeadlines(30)])
      .then(([s, d]) => { setSummary(s); setDeadlines(d) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading…</div>

  const dist: Record<string, number> = summary ? {
    High:   summary.high_risk,
    Medium: summary.medium_risk,
    Low:    summary.low_risk,
  } : {}

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">
          Welcome back, <span className="font-medium">{user?.name}</span>
          {isAdmin(user) ? ' · Viewing all students' : ' · Viewing your students'}
        </p>
      </div>

      {/* Stats cards */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatsCard
            title={isAdmin(user) ? 'Total Students' : 'My Students'}
            value={summary.total_students}
            icon={Users}
            color="indigo"
          />
          <StatsCard
            title="High Risk"
            value={summary.high_risk}
            sub="Needs attention"
            icon={AlertTriangle}
            color="red"
          />
          <StatsCard
            title="Overdue Milestones"
            value={summary.overdue_students}
            sub="Students affected"
            icon={AlertTriangle}
            color="amber"
          />
          <StatsCard
            title="Due in 30 Days"
            value={summary.upcoming_30_days}
            sub="Upcoming milestones"
            icon={Clock}
            color="blue"
          />
        </div>
      )}

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk distribution */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold text-gray-800">Risk Distribution</h2>
          </div>
          <RiskChart distribution={dist} />
        </div>

        {/* Upcoming deadlines */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold text-gray-800">Upcoming Deadlines (30 days)</h2>
          </div>

          {deadlines.length === 0 ? (
            <p className="text-sm text-gray-400 py-8 text-center">No upcoming deadlines</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {deadlines.slice(0, 10).map((d, i) => (
                <div key={i} className="flex items-start justify-between py-2 border-b border-gray-50 last:border-0">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{d.student_name}</p>
                    <p className="text-xs text-gray-500">{d.milestone}</p>
                  </div>
                  <div className="ml-3 text-right flex-shrink-0">
                    <p className="text-xs font-semibold text-indigo-600">{d.days_left}d left</p>
                    <p className="text-xs text-gray-400">{d.expected_date}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
