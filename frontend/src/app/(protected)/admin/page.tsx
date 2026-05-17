'use client'
import { useEffect, useState } from 'react'
import { UserPlus, Users } from 'lucide-react'
import {
  getPrograms, getFaculties, getCountries, getDisciplines,
  getFundingTypes, getCampuses, getSupervisors,
  createStudent, createSupervisor,
} from '@/lib/api'

// ── Helpers ──────────────────────────────────────────────────────────────────
function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-600 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

const inputCls = "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
const selectCls = inputCls

// ── Add Student Form ──────────────────────────────────────────────────────────
function AddStudentForm() {
  const [programs, setPrograms]     = useState<any[]>([])
  const [countries, setCountries]   = useState<any[]>([])
  const [disciplines, setDisciplines] = useState<any[]>([])
  const [funding, setFunding]       = useState<any[]>([])
  const [campuses, setCampuses]     = useState<any[]>([])
  const [supervisors, setSupervisors] = useState<any[]>([])
  const [loading, setLoading]       = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult]         = useState<{ ok: boolean; msg: string } | null>(null)

  const [form, setForm] = useState({
    student_id_number: '', student_name: '', email: '',
    program_id: '', degree_type: 'Master', study_method: 'Full-time',
    enrollment_date: '', campus_id: '',
    gender: '', date_of_birth: '', country_id: '', marital_status: '',
    num_children: '0', discipline_id: '', entry_gpa: '',
    is_cross_discipline: false, funding_id: '',
    has_external_work: false, weekly_work_hours: '0',
    in_research_group: false, family_support: '',
    supervisor_id: '',
  })

  useEffect(() => {
    Promise.all([getPrograms(), getCountries(), getDisciplines(), getFundingTypes(), getCampuses(), getSupervisors()])
      .then(([p, c, d, f, ca, s]) => {
        setPrograms(p); setCountries(c); setDisciplines(d)
        setFunding(f); setCampuses(ca); setSupervisors(s)
      })
      .finally(() => setLoading(false))
  }, [])

  function set(k: string, v: any) { setForm(f => ({ ...f, [k]: v })) }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setResult(null)
    try {
      const payload: any = {
        student_id_number: form.student_id_number,
        student_name:      form.student_name,
        email:             form.email || null,
        program_id:        parseInt(form.program_id),
        degree_type:       form.degree_type,
        study_method:      form.study_method,
        enrollment_date:   form.enrollment_date,
        campus_id:         parseInt(form.campus_id),
        gender:            form.gender || null,
        date_of_birth:     form.date_of_birth || null,
        country_id:        form.country_id ? parseInt(form.country_id) : null,
        marital_status:    form.marital_status || null,
        num_children:      parseInt(form.num_children) || 0,
        discipline_id:     form.discipline_id ? parseInt(form.discipline_id) : null,
        entry_gpa:         form.entry_gpa ? parseFloat(form.entry_gpa) : null,
        is_cross_discipline: form.is_cross_discipline,
        funding_id:        form.funding_id ? parseInt(form.funding_id) : null,
        has_external_work: form.has_external_work,
        weekly_work_hours: parseFloat(form.weekly_work_hours) || 0,
        in_research_group: form.in_research_group,
        family_support:    form.family_support ? parseInt(form.family_support) : null,
        supervisor_id:     form.supervisor_id ? parseInt(form.supervisor_id) : null,
      }
      const res = await createStudent(payload)
      setResult({ ok: true, msg: res.message })
      // Reset form
      setForm(f => ({ ...f, student_id_number: '', student_name: '', email: '' }))
    } catch (e: any) {
      setResult({ ok: false, msg: e.message })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="py-16 text-center text-gray-400">Loading form data…</div>

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Section: Identity */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Identity</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="Matric Number" required>
            <input className={inputCls} value={form.student_id_number}
              onChange={e => set('student_id_number', e.target.value)} placeholder="e.g. GS12345" required />
          </Field>
          <Field label="Full Name" required>
            <input className={inputCls} value={form.student_name}
              onChange={e => set('student_name', e.target.value)} placeholder="Full name" required />
          </Field>
          <Field label="Email">
            <input className={inputCls} type="email" value={form.email}
              onChange={e => set('email', e.target.value)} placeholder="email@university.edu" />
          </Field>
          <Field label="Gender">
            <select className={selectCls} value={form.gender} onChange={e => set('gender', e.target.value)}>
              <option value="">— Select —</option>
              <option>Male</option><option>Female</option><option>Other</option>
            </select>
          </Field>
          <Field label="Date of Birth">
            <input className={inputCls} type="date" value={form.date_of_birth}
              onChange={e => set('date_of_birth', e.target.value)} />
          </Field>
          <Field label="Nationality">
            <select className={selectCls} value={form.country_id} onChange={e => set('country_id', e.target.value)}>
              <option value="">— Select country —</option>
              {countries.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Marital Status">
            <select className={selectCls} value={form.marital_status} onChange={e => set('marital_status', e.target.value)}>
              <option value="">— Select —</option>
              <option>Single</option><option>Married</option><option>Divorced</option><option>Widowed</option>
            </select>
          </Field>
          <Field label="Number of Children">
            <input className={inputCls} type="number" min="0" value={form.num_children}
              onChange={e => set('num_children', e.target.value)} />
          </Field>
        </div>
      </div>

      {/* Section: Academic */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Academic</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="Programme" required>
            <select className={selectCls} value={form.program_id} onChange={e => set('program_id', e.target.value)} required>
              <option value="">— Select programme —</option>
              {programs.map(p => <option key={p.id} value={p.id}>{p.short} — {p.faculty}</option>)}
            </select>
          </Field>
          <Field label="Degree Type" required>
            <select className={selectCls} value={form.degree_type} onChange={e => set('degree_type', e.target.value)}>
              <option>Master</option><option>PhD</option>
            </select>
          </Field>
          <Field label="Study Method" required>
            <select className={selectCls} value={form.study_method} onChange={e => set('study_method', e.target.value)}>
              <option>Full-time</option><option>Part-time</option>
            </select>
          </Field>
          <Field label="Enrollment Date" required>
            <input className={inputCls} type="date" value={form.enrollment_date}
              onChange={e => set('enrollment_date', e.target.value)} required />
          </Field>
          <Field label="Campus" required>
            <select className={selectCls} value={form.campus_id} onChange={e => set('campus_id', e.target.value)} required>
              <option value="">— Select campus —</option>
              {campuses.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Discipline">
            <select className={selectCls} value={form.discipline_id} onChange={e => set('discipline_id', e.target.value)}>
              <option value="">— Select —</option>
              {disciplines.map(d => <option key={d.id} value={d.id}>{d.name} ({d.group})</option>)}
            </select>
          </Field>
          <Field label="Entry GPA">
            <input className={inputCls} type="number" step="0.01" min="0" max="4" value={form.entry_gpa}
              onChange={e => set('entry_gpa', e.target.value)} placeholder="0.00 – 4.00" />
          </Field>
          <Field label="Cross-discipline">
            <div className="flex items-center gap-2 mt-2">
              <input type="checkbox" id="cross" checked={form.is_cross_discipline}
                onChange={e => set('is_cross_discipline', e.target.checked)} className="w-4 h-4 accent-indigo-600" />
              <label htmlFor="cross" className="text-sm text-gray-600">Yes, cross-discipline study</label>
            </div>
          </Field>
        </div>
      </div>

      {/* Section: Financial & Social */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Financial & Social Support</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="Funding Type">
            <select className={selectCls} value={form.funding_id} onChange={e => set('funding_id', e.target.value)}>
              <option value="">— Select —</option>
              {funding.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </Field>
          <Field label="External Work">
            <div className="flex items-center gap-2 mt-2">
              <input type="checkbox" id="extwork" checked={form.has_external_work}
                onChange={e => set('has_external_work', e.target.checked)} className="w-4 h-4 accent-indigo-600" />
              <label htmlFor="extwork" className="text-sm text-gray-600">Has external employment</label>
            </div>
          </Field>
          {form.has_external_work && (
            <Field label="Weekly Work Hours">
              <input className={inputCls} type="number" min="0" max="60" value={form.weekly_work_hours}
                onChange={e => set('weekly_work_hours', e.target.value)} placeholder="hrs/week" />
            </Field>
          )}
          <Field label="Research Group">
            <div className="flex items-center gap-2 mt-2">
              <input type="checkbox" id="rg" checked={form.in_research_group}
                onChange={e => set('in_research_group', e.target.checked)} className="w-4 h-4 accent-indigo-600" />
              <label htmlFor="rg" className="text-sm text-gray-600">Member of research group</label>
            </div>
          </Field>
          <Field label="Family Support (1–5)">
            <select className={selectCls} value={form.family_support} onChange={e => set('family_support', e.target.value)}>
              <option value="">— Select —</option>
              <option value="1">1 — Very Low</option>
              <option value="2">2 — Low</option>
              <option value="3">3 — Moderate</option>
              <option value="4">4 — High</option>
              <option value="5">5 — Very High</option>
            </select>
          </Field>
        </div>
      </div>

      {/* Section: Supervisor */}
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Supervisor Assignment</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Main Supervisor">
            <select className={selectCls} value={form.supervisor_id} onChange={e => set('supervisor_id', e.target.value)}>
              <option value="">— Assign later —</option>
              {supervisors.map(s => <option key={s.supervisor_id} value={s.supervisor_id}>{s.name} ({s.staff_id})</option>)}
            </select>
          </Field>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className={`px-4 py-3 rounded-lg text-sm font-medium ${
          result.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
        }`}>
          {result.ok ? '✅' : '❌'} {result.msg}
        </div>
      )}

      <button type="submit" disabled={submitting}
        className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-semibold rounded-lg transition">
        {submitting ? 'Creating…' : 'Create Student'}
      </button>
    </form>
  )
}

// ── Add Lecturer Form ─────────────────────────────────────────────────────────
function AddLecturerForm() {
  const [faculties, setFaculties] = useState<any[]>([])
  const [loading, setLoading]     = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult]       = useState<{ ok: boolean; msg: string } | null>(null)
  const [showPw, setShowPw]       = useState(false)

  const [form, setForm] = useState({
    staff_id: '', name: '', email: '',
    faculty_id: '', role: 'Supervisor', password: '', confirm_pw: '',
  })

  useEffect(() => {
    getFaculties().then(setFaculties).finally(() => setLoading(false))
  }, [])

  function set(k: string, v: any) { setForm(f => ({ ...f, [k]: v })) }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (form.password !== form.confirm_pw) {
      setResult({ ok: false, msg: 'Passwords do not match.' })
      return
    }
    if (form.password.length < 6) {
      setResult({ ok: false, msg: 'Password must be at least 6 characters.' })
      return
    }
    setSubmitting(true)
    setResult(null)
    try {
      const res = await createSupervisor({
        staff_id:   form.staff_id,
        name:       form.name,
        email:      form.email,
        faculty_id: parseInt(form.faculty_id),
        role:       form.role,
        password:   form.password,
      })
      setResult({ ok: true, msg: res.message })
      setForm(f => ({ ...f, staff_id: '', name: '', email: '', password: '', confirm_pw: '' }))
    } catch (e: any) {
      setResult({ ok: false, msg: e.message })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="py-16 text-center text-gray-400">Loading…</div>

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Account Details</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Staff ID" required>
            <input className={inputCls} value={form.staff_id}
              onChange={e => set('staff_id', e.target.value)} placeholder="e.g. MU081217" required />
          </Field>
          <Field label="Full Name" required>
            <input className={inputCls} value={form.name}
              onChange={e => set('name', e.target.value)} placeholder="Dr. / Prof. ..." required />
          </Field>
          <Field label="Email" required>
            <input className={inputCls} type="email" value={form.email}
              onChange={e => set('email', e.target.value)} placeholder="staff@university.edu" required />
          </Field>
          <Field label="Faculty" required>
            <select className={selectCls} value={form.faculty_id} onChange={e => set('faculty_id', e.target.value)} required>
              <option value="">— Select faculty —</option>
              {faculties.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </Field>
          <Field label="Role" required>
            <select className={selectCls} value={form.role} onChange={e => set('role', e.target.value)}>
              <option value="Supervisor">Supervisor (Lecturer)</option>
              <option value="Admin">Admin only</option>
              <option value="Both">Both (Supervisor + Admin)</option>
            </select>
          </Field>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-3 pb-1 border-b">Login Password</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Password" required>
            <div className="relative">
              <input className={inputCls} type={showPw ? 'text' : 'password'} value={form.password}
                onChange={e => set('password', e.target.value)} placeholder="Min. 6 characters" required />
              <button type="button" onClick={() => setShowPw(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs hover:text-gray-600">
                {showPw ? 'Hide' : 'Show'}
              </button>
            </div>
          </Field>
          <Field label="Confirm Password" required>
            <input className={inputCls} type={showPw ? 'text' : 'password'} value={form.confirm_pw}
              onChange={e => set('confirm_pw', e.target.value)} placeholder="Repeat password" required />
          </Field>
        </div>
      </div>

      {result && (
        <div className={`px-4 py-3 rounded-lg text-sm font-medium ${
          result.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
        }`}>
          {result.ok ? '✅' : '❌'} {result.msg}
        </div>
      )}

      <button type="submit" disabled={submitting}
        className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-semibold rounded-lg transition">
        {submitting ? 'Creating…' : 'Create Account'}
      </button>
    </form>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const [tab, setTab] = useState<'student' | 'lecturer'>('student')

  return (
    <div className="max-w-5xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
        <p className="text-gray-500 text-sm">Create student records and lecturer accounts</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setTab('student')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
            tab === 'student'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Users className="w-4 h-4" />
          Add Student
        </button>
        <button
          onClick={() => setTab('lecturer')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
            tab === 'lecturer'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <UserPlus className="w-4 h-4" />
          Add Lecturer
        </button>
      </div>

      {/* Form card */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
        {tab === 'student' ? <AddStudentForm /> : <AddLecturerForm />}
      </div>
    </div>
  )
}
