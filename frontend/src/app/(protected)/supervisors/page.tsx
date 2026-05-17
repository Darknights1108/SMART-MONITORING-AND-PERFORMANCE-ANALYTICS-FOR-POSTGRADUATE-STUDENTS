'use client'
import { useEffect, useState } from 'react'
import { Users, Search } from 'lucide-react'
import { getSupervisors } from '@/lib/api'

export default function SupervisorsPage() {
  const [supervisors, setSupervisors] = useState<any[]>([])
  const [query, setQuery]  = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getSupervisors()
      .then(setSupervisors)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = supervisors.filter(s =>
    !query ||
    s.name.toLowerCase().includes(query.toLowerCase()) ||
    s.staff_id.toLowerCase().includes(query.toLowerCase()) ||
    (s.faculty || '').toLowerCase().includes(query.toLowerCase())
  )

  const roleColor = (role: string) =>
    role === 'Admin' ? 'bg-amber-100 text-amber-700' :
    role === 'Both'  ? 'bg-purple-100 text-purple-700' :
                       'bg-blue-100 text-blue-700'

  return (
    <div className="max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Supervisors</h1>
        <p className="text-gray-500 text-sm">All lecturers and administrators</p>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by name, ID or faculty…"
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-gray-400">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wide text-left">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Staff ID</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Faculty</th>
                  <th className="px-4 py-3 text-center">Students</th>
                  <th className="px-4 py-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(s => (
                  <tr key={s.supervisor_id} className="hover:bg-gray-50/50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-700 text-sm font-bold flex-shrink-0">
                          {s.name.charAt(0)}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">{s.name}</p>
                          <p className="text-xs text-gray-400">{s.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{s.staff_id}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${roleColor(s.role)}`}>
                        {s.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs max-w-[200px] truncate">{s.faculty}</td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <Users className="w-3.5 h-3.5 text-gray-400" />
                        <span className="font-semibold text-gray-700">{s.student_count}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                        s.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </span>
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
