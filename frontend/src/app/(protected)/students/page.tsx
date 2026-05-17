'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search } from 'lucide-react'
import RiskBadge from '@/components/RiskBadge'
import { getStudents } from '@/lib/api'
import { getUser, isAdmin } from '@/lib/auth'

export default function StudentsPage() {
  const router = useRouter()
  const user   = getUser()
  const [students, setStudents] = useState<any[]>([])
  const [query, setQuery]       = useState('')
  const [filter, setFilter]     = useState<string>('All')
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    getStudents()
      .then(setStudents)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const filtered = students.filter(s => {
    const matchQ = !query ||
      s.student_name.toLowerCase().includes(query.toLowerCase()) ||
      s.student_id_number.toLowerCase().includes(query.toLowerCase()) ||
      (s.supervisor_name || '').toLowerCase().includes(query.toLowerCase())
    const matchR = filter === 'All' || s.risk_label === filter
    return matchQ && matchR
  })

  return (
    <div className="space-y-5 max-w-7xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Students</h1>
          <p className="text-gray-500 text-sm">
            {isAdmin(user) ? 'All students in the system' : 'Your supervised students'}
          </p>
        </div>
        <span className="text-sm text-gray-400">{filtered.length} students</span>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search by name, ID or supervisor…"
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-2">
          {['All', 'High', 'Medium', 'Low'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-2 text-xs font-semibold rounded-lg border transition ${
                filter === f
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-gray-400">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="py-20 text-center text-gray-400">No students found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  <th className="px-4 py-3">Student</th>
                  <th className="px-4 py-3">Program</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Mode</th>
                  {isAdmin(user) && <th className="px-4 py-3">Supervisor</th>}
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(s => (
                  <tr key={s.student_id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{s.student_name}</p>
                      <p className="text-xs text-gray-400">{s.student_id_number}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{s.program}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        s.degree_type === 'PhD'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-blue-100 text-blue-700'
                      }`}>
                        {s.degree_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{s.study_method}</td>
                    {isAdmin(user) && (
                      <td className="px-4 py-3 text-gray-600 text-xs">{s.supervisor_name || '—'}</td>
                    )}
                    <td className="px-4 py-3">
                      <RiskBadge label={s.risk_label} score={s.risk_score} />
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => router.push(`/students/${s.student_id}`)}
                        className="text-xs text-indigo-600 hover:underline font-medium"
                      >
                        View →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
