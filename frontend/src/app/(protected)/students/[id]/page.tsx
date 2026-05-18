'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft, User, BookOpen, AlertTriangle,
  CheckCircle, Clock, Pencil, X, Save, Loader2, Plus,
} from 'lucide-react'
import RiskBadge from '@/components/RiskBadge'
import {
  getStudent, updateStudent, updateMilestone,
  createPpm, updatePpm,
  getPrograms, getCountries, getDisciplines,
  getFundingTypes, getCampuses,
} from '@/lib/api'
import { getUser } from '@/lib/auth'

// ── helpers ───────────────────────────────────────────────────────────────────
const statusIcon = (s: string) => {
  if (s === 'Completed') return <CheckCircle className="w-4 h-4 text-green-500" />
  if (s === 'Overdue')   return <AlertTriangle className="w-4 h-4 text-red-500" />
  return <Clock className="w-4 h-4 text-amber-500" />
}
const statusColor = (s: string) =>
  s === 'Completed' ? 'bg-green-100 text-green-700' :
  s === 'Overdue'   ? 'bg-red-100 text-red-700'     :
                      'bg-amber-100 text-amber-700'

// ── Edit Modal ────────────────────────────────────────────────────────────────
function EditModal({
  data, onClose, onSaved,
}: {
  data: any
  onClose: () => void
  onSaved: (updated: any) => void
}) {
  const [form, setForm] = useState({
    student_name:       data.student_name       ?? '',
    email:              data.email              ?? '',
    gender:             data.gender             ?? '',
    date_of_birth:      data.date_of_birth      ?? '',
    country_id:         data.country_id         ?? '',
    marital_status:     data.marital_status     ?? '',
    num_children:       data.num_children       ?? 0,
    program_id:         data.program_id         ?? '',
    degree_type:        data.degree_type        ?? 'Master',
    study_method:       data.study_method       ?? 'Full-time',
    enrollment_date:    data.enrollment_date    ?? '',
    entry_gpa:          data.entry_gpa          ?? '',
    is_cross_discipline: data.is_cross_discipline ?? false,
    discipline_id:      data.discipline_id      ?? '',
    campus_id:          data.campus_id          ?? '',
    funding_id:         data.funding_id         ?? '',
    has_external_work:  data.has_external_work  ?? false,
    weekly_work_hours:  data.weekly_work_hours  ?? 0,
    in_research_group:  data.in_research_group  ?? false,
    family_support:     data.family_support     ?? '',
    program_status:     data.program_status     ?? 'Active in Program',
  })
  const [lookups, setLookups] = useState<any>({
    programs: [], countries: [], disciplines: [], funding: [], campuses: [],
  })
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState('')
  const [tab, setTab]         = useState<'personal' | 'academic' | 'other'>('personal')

  useEffect(() => {
    Promise.all([getPrograms(), getCountries(), getDisciplines(), getFundingTypes(), getCampuses()])
      .then(([programs, countries, disciplines, funding, campuses]) =>
        setLookups({ programs, countries, disciplines, funding, campuses })
      )
      .catch(() => {})
  }, [])

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }))

  async function handleSave() {
    setSaving(true); setError('')
    try {
      const payload: any = {
        student_name:       form.student_name      || undefined,
        email:              form.email             || undefined,
        gender:             form.gender            || undefined,
        date_of_birth:      form.date_of_birth     || undefined,
        country_id:         form.country_id        ? Number(form.country_id) : undefined,
        marital_status:     form.marital_status    || undefined,
        num_children:       Number(form.num_children),
        program_id:         form.program_id        ? Number(form.program_id) : undefined,
        degree_type:        form.degree_type       || undefined,
        study_method:       form.study_method      || undefined,
        enrollment_date:    form.enrollment_date   || undefined,
        entry_gpa:          form.entry_gpa !== ''  ? Number(form.entry_gpa) : undefined,
        is_cross_discipline: form.is_cross_discipline,
        discipline_id:      form.discipline_id     ? Number(form.discipline_id) : undefined,
        campus_id:          form.campus_id         ? Number(form.campus_id) : undefined,
        funding_id:         form.funding_id        ? Number(form.funding_id) : undefined,
        has_external_work:  form.has_external_work,
        weekly_work_hours:  Number(form.weekly_work_hours),
        in_research_group:  form.in_research_group,
        family_support:     form.family_support !== '' ? Number(form.family_support) : undefined,
        program_status:     form.program_status    || undefined,
      }
      await updateStudent(data.student_id, payload)
      // Find updated program name for display
      const prog = lookups.programs.find((p: any) => p.id === payload.program_id)
      onSaved({
        ...data,
        ...payload,
        program_full: prog?.full ?? data.program_full,
        program:      prog?.short ?? data.program,
      })
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const tabCls = (t: string) =>
    `px-4 py-2 text-sm font-medium border-b-2 transition ${
      tab === t
        ? 'border-indigo-600 text-indigo-600'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`

  const fieldCls = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
  const labelCls = 'block text-xs font-medium text-gray-600 mb-1'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Edit Student</h2>
            <p className="text-xs text-gray-400 mt-0.5">{data.student_id_number}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 px-6 flex-shrink-0">
          <button className={tabCls('personal')} onClick={() => setTab('personal')}>Personal</button>
          <button className={tabCls('academic')} onClick={() => setTab('academic')}>Academic</button>
          <button className={tabCls('other')}    onClick={() => setTab('other')}>Financial & Social</button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto flex-1">
          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-4">
              {error}
            </p>
          )}

          {tab === 'personal' && (
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className={labelCls}>Full Name</label>
                <input value={form.student_name} onChange={e => set('student_name', e.target.value)} className={fieldCls} />
              </div>
              <div className="col-span-2">
                <label className={labelCls}>Email</label>
                <input type="email" value={form.email} onChange={e => set('email', e.target.value)} className={fieldCls} />
              </div>
              <div>
                <label className={labelCls}>Gender</label>
                <select value={form.gender} onChange={e => set('gender', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  <option>Male</option><option>Female</option><option>Other</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Date of Birth</label>
                <input type="date" value={form.date_of_birth} onChange={e => set('date_of_birth', e.target.value)} className={fieldCls} />
              </div>
              <div>
                <label className={labelCls}>Country</label>
                <select value={form.country_id} onChange={e => set('country_id', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  {lookups.countries.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Marital Status</label>
                <select value={form.marital_status} onChange={e => set('marital_status', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  <option>Single</option><option>Married</option>
                  <option>Divorced</option><option>Widowed</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Number of Children</label>
                <input type="number" min="0" value={form.num_children} onChange={e => set('num_children', e.target.value)} className={fieldCls} />
              </div>
            </div>
          )}

          {tab === 'academic' && (
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className={labelCls}>Program</label>
                <select value={form.program_id} onChange={e => set('program_id', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  {lookups.programs.map((p: any) => <option key={p.id} value={p.id}>{p.short} — {p.full}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Degree Type</label>
                <select value={form.degree_type} onChange={e => set('degree_type', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option>Master</option><option>PhD</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Study Mode</label>
                <select value={form.study_method} onChange={e => set('study_method', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option>Full-time</option><option>Part-time</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Enrollment Date</label>
                <input type="date" value={form.enrollment_date} onChange={e => set('enrollment_date', e.target.value)} className={fieldCls} />
              </div>
              <div>
                <label className={labelCls}>Entry GPA</label>
                <input type="number" step="0.01" min="0" max="4" value={form.entry_gpa} onChange={e => set('entry_gpa', e.target.value)} className={fieldCls} />
              </div>
              <div>
                <label className={labelCls}>Campus</label>
                <select value={form.campus_id} onChange={e => set('campus_id', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  {lookups.campuses.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Discipline</label>
                <select value={form.discipline_id} onChange={e => set('discipline_id', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  {lookups.disciplines.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Program Status</label>
                <select value={form.program_status} onChange={e => set('program_status', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option>Active in Program</option>
                  <option>Graduated On-time</option>
                  <option>Graduated Delayed</option>
                  <option>Dropped Out</option>
                  <option>Withdrawn</option>
                </select>
              </div>
              <div className="col-span-2 flex items-center gap-2 pt-1">
                <input type="checkbox" id="cross_disc" checked={form.is_cross_discipline}
                  onChange={e => set('is_cross_discipline', e.target.checked)}
                  className="w-4 h-4 accent-indigo-600" />
                <label htmlFor="cross_disc" className="text-sm text-gray-700">Cross-discipline student</label>
              </div>
            </div>
          )}

          {tab === 'other' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Funding Type</label>
                <select value={form.funding_id} onChange={e => set('funding_id', e.target.value)} className={`${fieldCls} bg-white`}>
                  <option value="">— Select —</option>
                  {lookups.funding.map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Family Support <span className="text-gray-400 font-normal">(1–5)</span></label>
                <input type="number" min="1" max="5" value={form.family_support}
                  onChange={e => set('family_support', e.target.value)} className={fieldCls} />
              </div>
              <div className="col-span-2 flex items-center gap-2">
                <input type="checkbox" id="ext_work" checked={form.has_external_work}
                  onChange={e => set('has_external_work', e.target.checked)}
                  className="w-4 h-4 accent-indigo-600" />
                <label htmlFor="ext_work" className="text-sm text-gray-700">Has external work</label>
              </div>
              {form.has_external_work && (
                <div>
                  <label className={labelCls}>Weekly Work Hours</label>
                  <input type="number" min="0" step="0.5" value={form.weekly_work_hours}
                    onChange={e => set('weekly_work_hours', e.target.value)} className={fieldCls} />
                </div>
              )}
              <div className="col-span-2 flex items-center gap-2">
                <input type="checkbox" id="research" checked={form.in_research_group}
                  onChange={e => set('in_research_group', e.target.checked)}
                  className="w-4 h-4 accent-indigo-600" />
                <label htmlFor="research" className="text-sm text-gray-700">In research group</label>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-2 flex-shrink-0">
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

// ── Milestone inline edit row ─────────────────────────────────────────────────
function MilestoneRow({
  m, studentId, isAdmin, onSaved,
}: {
  m: any
  studentId: number
  isAdmin: boolean
  onSaved: (updated: any) => void
}) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    expected_date: m.expected_date ?? '',
    actual_date:   m.actual_date   ?? '',
    status:        m.status        ?? 'Pending',
    remarks:       m.remarks       ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr]       = useState('')

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  async function handleSave() {
    setSaving(true); setErr('')
    try {
      const payload: any = {
        expected_date: form.expected_date || null,
        actual_date:   form.actual_date   || null,
        status:        form.status,
        remarks:       form.remarks       || null,
      }
      await updateMilestone(studentId, m.milestone_id, payload)
      onSaved({ ...m, ...payload })
      setEditing(false)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  function handleCancel() {
    setForm({
      expected_date: m.expected_date ?? '',
      actual_date:   m.actual_date   ?? '',
      status:        m.status        ?? 'Pending',
      remarks:       m.remarks       ?? '',
    })
    setErr('')
    setEditing(false)
  }

  const fieldCls = 'border border-gray-200 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500'

  if (!editing) {
    return (
      <div className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
        <div className="mt-0.5">{statusIcon(m.status)}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-gray-800">{m.name}</p>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor(m.status)}`}>
              {m.status}
            </span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5 flex gap-3 flex-wrap">
            <span>Expected: {m.expected_date ?? '—'}</span>
            {m.actual_date && <span>Actual: {m.actual_date}</span>}
          </div>
          {m.remarks && <p className="text-xs text-gray-500 mt-1 italic">{m.remarks}</p>}
        </div>
        {isAdmin && (
          <button
            onClick={() => setEditing(true)}
            className="flex-shrink-0 p-1 text-gray-300 hover:text-indigo-500 transition"
            title="Edit milestone"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="py-3 border-b border-indigo-50 last:border-0 bg-indigo-50/30 rounded-lg px-3 -mx-3">
      <p className="text-sm font-medium text-gray-800 mb-3">{m.name}</p>

      {err && <p className="text-xs text-red-600 mb-2">{err}</p>}

      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Expected date</label>
          <input type="date" value={form.expected_date} onChange={e => set('expected_date', e.target.value)}
            className={`w-full ${fieldCls}`} />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Actual / submission date</label>
          <input type="date" value={form.actual_date} onChange={e => set('actual_date', e.target.value)}
            className={`w-full ${fieldCls}`} />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Status</label>
          <select value={form.status} onChange={e => set('status', e.target.value)}
            className={`w-full ${fieldCls} bg-white`}>
            <option>Pending</option>
            <option>Completed</option>
            <option>Overdue</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Remarks</label>
          <input value={form.remarks} onChange={e => set('remarks', e.target.value)}
            placeholder="Optional notes…"
            className={`w-full ${fieldCls}`} />
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button onClick={handleCancel}
          className="px-3 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition">
          Cancel
        </button>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-md transition">
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// ── PPM result badge ──────────────────────────────────────────────────────────
const ppmColor = (r: string | null) =>
  r === 'US' ? 'bg-red-100 text-red-700' :
  r === 'S'  ? 'bg-green-100 text-green-700' :
               'bg-gray-100 text-gray-500'

// ── PPM inline edit row ───────────────────────────────────────────────────────
function PpmRow({
  p, studentId, isAdmin, onSaved,
}: {
  p: any
  studentId: number
  isAdmin: boolean
  onSaved: (updated: any) => void
}) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    result:        p.result        ?? '',
    verify_status: p.verified ? 'Y' : 'N',
    verify_date:   p.verify_date   ?? '',
    remarks:       p.remarks       ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr]       = useState('')
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  async function handleSave() {
    setSaving(true); setErr('')
    try {
      const payload = {
        result:        form.result        || null,
        verify_status: form.verify_status,
        verify_date:   form.verify_date   || null,
        remarks:       form.remarks       || null,
      }
      await updatePpm(studentId, p.year, p.cycle, payload)
      onSaved({ ...p, ...payload, verified: payload.verify_status === 'Y' })
      setEditing(false)
    } catch (e: any) { setErr(e.message) }
    finally { setSaving(false) }
  }

  const fieldCls = 'border border-gray-200 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white w-full'

  if (!editing) return (
    <div className="flex items-center gap-2 text-xs py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-gray-600 flex-1">Year {p.year} · Cycle {p.cycle}</span>
      <span className={`font-bold px-2 py-0.5 rounded-full ${ppmColor(p.result)}`}>
        {p.result ?? '—'}
      </span>
      {p.verified && (
        <span className="text-gray-400" title={`Verified ${p.verify_date ?? ''}`}>✓</span>
      )}
      {isAdmin && (
        <button onClick={() => setEditing(true)}
          className="p-0.5 text-gray-300 hover:text-indigo-500 transition" title="Edit PPM">
          <Pencil className="w-3 h-3" />
        </button>
      )}
    </div>
  )

  return (
    <div className="py-2 px-3 -mx-3 bg-indigo-50/30 rounded-lg border-b border-indigo-50 last:border-0 mb-1">
      <p className="text-xs font-medium text-gray-700 mb-2">Year {p.year} · Cycle {p.cycle}</p>
      {err && <p className="text-xs text-red-600 mb-1">{err}</p>}
      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Result</label>
          <select value={form.result} onChange={e => set('result', e.target.value)} className={fieldCls}>
            <option value="">— Pending —</option>
            <option value="S">S (Satisfactory)</option>
            <option value="US">US (Unsatisfactory)</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Verified</label>
          <select value={form.verify_status} onChange={e => set('verify_status', e.target.value)} className={fieldCls}>
            <option value="N">No</option>
            <option value="Y">Yes</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Verify date</label>
          <input type="date" value={form.verify_date} onChange={e => set('verify_date', e.target.value)}
            className={fieldCls} />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Remarks</label>
          <input value={form.remarks} onChange={e => set('remarks', e.target.value)}
            placeholder="Optional…" className={fieldCls} />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={() => { setEditing(false); setErr('') }}
          className="px-3 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition">
          Cancel
        </button>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-md transition">
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// ── PPM add form ──────────────────────────────────────────────────────────────
function PpmAddForm({
  studentId, existingRecords, onAdded, onCancel,
}: {
  studentId: number
  existingRecords: any[]
  onAdded: (record: any) => void
  onCancel: () => void
}) {
  const currentYear = new Date().getFullYear()
  const [form, setForm] = useState({
    ppm_year:      String(currentYear),
    ppm_cycle:     '1',
    result:        '',
    verify_status: 'N',
    verify_date:   '',
    remarks:       '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr]       = useState('')
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  // Check how many cycles exist for the selected year
  const cyclesThisYear = existingRecords.filter(
    r => r.year === Number(form.ppm_year)
  ).length
  const cycleFull = cyclesThisYear >= 2

  // Auto-suggest next cycle for chosen year
  const usedCycles = existingRecords
    .filter(r => r.year === Number(form.ppm_year))
    .map(r => r.cycle)
  const suggestedCycle = usedCycles.includes(1) ? '2' : '1'

  async function handleAdd() {
    if (cycleFull) { setErr(`Year ${form.ppm_year} already has 2 cycles.`); return }
    setSaving(true); setErr('')
    try {
      const payload = {
        ppm_year:      Number(form.ppm_year),
        ppm_cycle:     Number(form.ppm_cycle),
        result:        form.result        || null,
        verify_status: form.verify_status,
        verify_date:   form.verify_date   || null,
        remarks:       form.remarks       || null,
      }
      await createPpm(studentId, payload)
      onAdded({
        year:        payload.ppm_year,
        cycle:       payload.ppm_cycle,
        result:      payload.result,
        verified:    payload.verify_status === 'Y',
        verify_date: payload.verify_date,
        remarks:     payload.remarks,
      })
    } catch (e: any) { setErr(e.message) }
    finally { setSaving(false) }
  }

  const fieldCls = 'border border-gray-200 rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white w-full'

  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <p className="text-xs font-medium text-gray-700 mb-2">Add PPM cycle</p>
      {err && <p className="text-xs text-red-600 mb-2">{err}</p>}
      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Year</label>
          <input type="number" min="2000" max="2099"
            value={form.ppm_year}
            onChange={e => {
              set('ppm_year', e.target.value)
              // auto-suggest cycle when year changes
              const cycs = existingRecords.filter(r => r.year === Number(e.target.value)).map(r => r.cycle)
              set('ppm_cycle', cycs.includes(1) ? '2' : '1')
            }}
            className={fieldCls} />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">
            Cycle
            {cycleFull && <span className="ml-1 text-red-500">(year full)</span>}
          </label>
          <select value={form.ppm_cycle} onChange={e => set('ppm_cycle', e.target.value)} className={fieldCls}>
            {!usedCycles.includes(1) && <option value="1">Cycle 1</option>}
            {!usedCycles.includes(2) && <option value="2">Cycle 2</option>}
            {cycleFull && <option value="">—</option>}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Result</label>
          <select value={form.result} onChange={e => set('result', e.target.value)} className={fieldCls}>
            <option value="">— Pending —</option>
            <option value="S">S (Satisfactory)</option>
            <option value="US">US (Unsatisfactory)</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Verified</label>
          <select value={form.verify_status} onChange={e => set('verify_status', e.target.value)} className={fieldCls}>
            <option value="N">No</option>
            <option value="Y">Yes</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Verify date</label>
          <input type="date" value={form.verify_date} onChange={e => set('verify_date', e.target.value)}
            className={fieldCls} />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Remarks</label>
          <input value={form.remarks} onChange={e => set('remarks', e.target.value)}
            placeholder="Optional…" className={fieldCls} />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel}
          className="px-3 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition">
          Cancel
        </button>
        <button onClick={handleAdd} disabled={saving || cycleFull}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-md transition">
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          {saving ? 'Adding…' : 'Add'}
        </button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function StudentDetailPage() {
  const { id }  = useParams()
  const router  = useRouter()
  const [data, setData]       = useState<any>(null)
  const [err, setErr]         = useState('')
  const [editing, setEditing] = useState(false)
  const [addingPpm, setAddingPpm] = useState(false)

  const currentUser = getUser()
  const isAdmin = currentUser?.role === 'Admin' || currentUser?.role === 'Both'

  useEffect(() => {
    if (!id) return
    getStudent(Number(id))
      .then(setData)
      .catch(e => setErr(e.message))
  }, [id])

  if (err)   return <div className="text-red-600 p-6">{err}</div>
  if (!data) return <div className="text-gray-400 p-6">Loading…</div>

  const ppmUs = data.ppm_records.filter((p: any) => p.result === 'US').length

  return (
    <div className="max-w-5xl space-y-6">
      {/* Back */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800"
      >
        <ArrowLeft className="w-4 h-4" /> Back to students
      </button>

      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-14 h-14 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-700 text-xl font-bold flex-shrink-0">
            {data.student_name.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-gray-900">{data.student_name}</h1>
            <p className="text-gray-500 text-sm">{data.student_id_number} · {data.email}</p>
            <p className="text-gray-400 text-xs mt-1">{data.program_full} · {data.faculty}</p>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            {data.risk && <RiskBadge label={data.risk.risk_label} score={data.risk.risk_score} />}
            {isAdmin && (
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-indigo-600 border border-indigo-200 rounded-lg hover:bg-indigo-50 transition"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-100">
          {[
            { label: 'Degree',         value: data.degree_type },
            { label: 'Study Mode',     value: data.study_method },
            { label: 'Enrolled',       value: data.enrollment_date },
            { label: 'Entry GPA',      value: data.entry_gpa ?? '—' },
            { label: 'Campus',         value: data.campus ?? '—' },
            { label: 'Country',        value: data.country ?? '—' },
            { label: 'Funding',        value: data.funding ?? '—' },
            { label: 'Weekly Work',    value: data.has_external_work ? `${data.weekly_work_hours}h/wk` : 'None' },
            { label: 'Family Support', value: data.family_support ? `${data.family_support}/5` : '—' },
          ].map(item => (
            <div key={item.label}>
              <p className="text-xs text-gray-400">{item.label}</p>
              <p className="text-sm font-medium text-gray-800 mt-0.5">{String(item.value)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Milestones */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <BookOpen className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold text-gray-800">Milestones</h2>
          </div>
          <div className="space-y-1">
            {data.milestones.map((m: any) => (
              <MilestoneRow
                key={m.milestone_id}
                m={m}
                studentId={data.student_id}
                isAdmin={isAdmin}
                onSaved={updated =>
                  setData((prev: any) => ({
                    ...prev,
                    milestones: prev.milestones.map((x: any) =>
                      x.milestone_id === updated.milestone_id ? updated : x
                    ),
                  }))
                }
              />
            ))}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-5">
          {/* Risk prediction */}
          {data.risk && (
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-gray-800">Risk Prediction</h2>
              </div>
              <div className="flex items-center gap-3 mb-3">
                <div className="flex-1 bg-gray-100 rounded-full h-2.5">
                  <div
                    className={`h-2.5 rounded-full ${
                      data.risk.risk_label === 'High'   ? 'bg-red-500' :
                      data.risk.risk_label === 'Medium' ? 'bg-amber-500' : 'bg-green-500'
                    }`}
                    style={{ width: `${data.risk.risk_score}%` }}
                  />
                </div>
                <span className="text-sm font-bold text-gray-700 w-12 text-right">
                  {data.risk.risk_score?.toFixed(0)}
                </span>
              </div>
              <RiskBadge label={data.risk.risk_label} />
              <ul className="mt-3 space-y-1">
                {data.risk.key_risk_factors.map((f: string, i: number) => (
                  <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                    <span className="text-amber-500 flex-shrink-0">•</span>{f}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-gray-400 mt-3">Updated: {data.risk.predicted_at?.slice(0, 10)}</p>
            </div>
          )}

          {/* PPM Records */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-gray-800">PPM Records</h2>
              </div>
              <div className="flex items-center gap-2">
                {ppmUs > 0 && (
                  <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-semibold">
                    {ppmUs} US
                  </span>
                )}
                {isAdmin && !addingPpm && (
                  <button
                    onClick={() => setAddingPpm(true)}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-2 py-1 rounded-lg transition"
                  >
                    <Plus className="w-3 h-3" /> Add cycle
                  </button>
                )}
              </div>
            </div>

            {data.ppm_records.length === 0 && !addingPpm ? (
              <p className="text-xs text-gray-400">No PPM records</p>
            ) : (
              <div>
                {data.ppm_records.map((p: any) => (
                  <PpmRow
                    key={`${p.year}-${p.cycle}`}
                    p={p}
                    studentId={data.student_id}
                    isAdmin={isAdmin}
                    onSaved={updated =>
                      setData((prev: any) => ({
                        ...prev,
                        ppm_records: prev.ppm_records.map((x: any) =>
                          x.year === updated.year && x.cycle === updated.cycle ? updated : x
                        ),
                      }))
                    }
                  />
                ))}
              </div>
            )}

            {addingPpm && (
              <PpmAddForm
                studentId={data.student_id}
                existingRecords={data.ppm_records}
                onAdded={record => {
                  setData((prev: any) => ({
                    ...prev,
                    ppm_records: [...prev.ppm_records, record]
                      .sort((a, b) => a.year !== b.year ? a.year - b.year : a.cycle - b.cycle),
                  }))
                  setAddingPpm(false)
                }}
                onCancel={() => setAddingPpm(false)}
              />
            )}
          </div>

          {/* Supervisors */}
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            <h2 className="font-semibold text-gray-800 mb-3">Supervisors</h2>
            {data.supervisors.map((s: any) => (
              <div key={s.supervisor_id} className="flex items-start gap-2 mb-2 last:mb-0">
                <div className="w-7 h-7 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-700 text-xs font-bold flex-shrink-0 mt-0.5">
                  {s.name.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-800">{s.name}</p>
                  <p className="text-xs text-gray-400">{s.role} · {s.staff_id}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {editing && (
        <EditModal
          data={data}
          onClose={() => setEditing(false)}
          onSaved={updated => { setData(updated); setEditing(false) }}
        />
      )}
    </div>
  )
}
