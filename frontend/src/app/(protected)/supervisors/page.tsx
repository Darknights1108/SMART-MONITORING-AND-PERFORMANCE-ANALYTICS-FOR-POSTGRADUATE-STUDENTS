'use client'
import { useEffect, useState } from 'react'
import { Users, Search, Pencil, X, Save, Loader2 } from 'lucide-react'
import { getSupervisors, updateSupervisor, getFaculties } from '@/lib/api'
import { getUser } from '@/lib/auth'

interface Supervisor {
  supervisor_id: number
  staff_id: string
  name: string
  email: string
  role: string
  faculty_id: number
  faculty: string
  is_active: boolean
  max_students: number | null
  student_count: number
}

interface Faculty { faculty_id: number; faculty_description: string }

// ── Edit Modal ────────────────────────────────────────────────────────────────
function EditModal({
  sup, faculties, onClose, onSaved,
}: {
  sup: Supervisor
  faculties: Faculty[]
  onClose: () => void
  onSaved: (updated: Supervisor) => void
}) {
  const [form, setForm] = useState({
    name:         sup.name,
    email:        sup.email,
    faculty_id:   sup.faculty_id,
    role:         sup.role,
    is_active:    sup.is_active,
    max_students: sup.max_students ?? '',   // '' means no limit
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))

  async function handleSave() {
    setSaving(true); setError('')
    try {
      const payload: any = {
        name:       form.name,
        email:      form.email,
        faculty_id: Number(form.faculty_id),
        role:       form.role,
        is_active:  form.is_active,
        max_students: form.max_students === '' ? null : Number(form.max_students),
      }
      await updateSupervisor(sup.supervisor_id, payload)
      const updatedFaculty = faculties.find(f => f.faculty_id === payload.faculty_id)
      onSaved({
        ...sup,
        ...payload,
        faculty: updatedFaculty?.faculty_description ?? sup.faculty,
      })
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Edit Supervisor</h2>
            <p className="text-xs text-gray-400 mt-0.5">{sup.staff_id}</p>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Full Name</label>
              <input value={form.name} onChange={e => set('name', e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
              <input type="email" value={form.email} onChange={e => set('email', e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Faculty</label>
              <select value={form.faculty_id} onChange={e => set('faculty_id', Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
                {faculties.map(f => (
                  <option key={f.faculty_id} value={f.faculty_id}>{f.faculty_description}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
              <select value={form.role} onChange={e => set('role', e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
                <option value="Supervisor">Supervisor</option>
                <option value="Admin">Admin</option>
                <option value="Both">Both</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Student Limit
                <span className="ml-1 text-gray-400 font-normal">(blank = unlimited)</span>
              </label>
              <input
                type="number" min="0" placeholder="No limit"
                value={form.max_students}
                onChange={e => set('max_students', e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
              <select value={form.is_active ? 'active' : 'inactive'}
                onChange={e => set('is_active', e.target.value === 'active')}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-2">
          <button onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-lg transition">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-lg transition">
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SupervisorsPage() {
  const [supervisors, setSupervisors] = useState<Supervisor[]>([])
  const [faculties, setFaculties]     = useState<Faculty[]>([])
  const [query, setQuery]             = useState('')
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [editing, setEditing]         = useState<Supervisor | null>(null)

  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'Admin' || currentUser?.role === 'Both'

  useEffect(() => {
    Promise.all([getSupervisors(), getFaculties()])
      .then(([sups, facs]) => { setSupervisors(sups); setFaculties(facs) })
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

  function handleSaved(updated: Supervisor) {
    setSupervisors(prev => prev.map(s =>
      s.supervisor_id === updated.supervisor_id ? updated : s
    ))
    setEditing(null)
  }

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
                  {isAdmin && <th className="px-4 py-3 text-center">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map(s => {
                  const atLimit = s.max_students !== null && s.student_count >= s.max_students
                  return (
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
                      <td className="px-4 py-3 text-gray-600 text-xs max-w-[180px] truncate">{s.faculty}</td>
                      <td className="px-4 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Users className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                          <span className={`font-semibold ${atLimit ? 'text-red-600' : 'text-gray-700'}`}>
                            {s.student_count}
                          </span>
                          {s.max_students !== null && (
                            <span className="text-xs text-gray-400">/ {s.max_students}</span>
                          )}
                        </div>
                        {atLimit && (
                          <span className="text-[10px] text-red-500 font-medium">Full</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                          s.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {s.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      {isAdmin && (
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => setEditing(s)}
                            className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-2 py-1 rounded-lg transition">
                            <Pencil className="w-3 h-3" />
                            Edit
                          </button>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <EditModal
          sup={editing}
          faculties={faculties}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
