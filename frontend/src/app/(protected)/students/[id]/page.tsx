'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, User, BookOpen, AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import RiskBadge from '@/components/RiskBadge'
import { getStudent } from '@/lib/api'

const statusIcon = (s: string) => {
  if (s === 'Completed') return <CheckCircle className="w-4 h-4 text-green-500" />
  if (s === 'Overdue')   return <AlertTriangle className="w-4 h-4 text-red-500" />
  return <Clock className="w-4 h-4 text-amber-500" />
}
const statusColor = (s: string) =>
  s === 'Completed' ? 'bg-green-100 text-green-700' :
  s === 'Overdue'   ? 'bg-red-100 text-red-700'     :
                      'bg-amber-100 text-amber-700'

export default function StudentDetailPage() {
  const { id }     = useParams()
  const router     = useRouter()
  const [data, setData] = useState<any>(null)
  const [err, setErr]   = useState('')

  useEffect(() => {
    if (!id) return
    getStudent(Number(id))
      .then(setData)
      .catch(e => setErr(e.message))
  }, [id])

  if (err)  return <div className="text-red-600 p-6">{err}</div>
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
          {data.risk && (
            <RiskBadge label={data.risk.risk_label} score={data.risk.risk_score} />
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-100">
          {[
            { label: 'Degree',       value: data.degree_type },
            { label: 'Study Mode',   value: data.study_method },
            { label: 'Enrolled',     value: data.enrollment_date },
            { label: 'Entry GPA',    value: data.entry_gpa ?? '—' },
            { label: 'Campus',       value: data.campus ?? '—' },
            { label: 'Country',      value: data.country ?? '—' },
            { label: 'Funding',      value: data.funding ?? '—' },
            { label: 'Weekly Work',  value: data.has_external_work ? `${data.weekly_work_hours}h/wk` : 'None' },
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
          <div className="space-y-3">
            {data.milestones.map((m: any, i: number) => (
              <div key={i} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                <div className="mt-0.5">{statusIcon(m.status)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium text-gray-800">{m.name}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor(m.status)}`}>
                      {m.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5 flex gap-3">
                    <span>Expected: {m.expected_date ?? '—'}</span>
                    {m.actual_date && <span>Actual: {m.actual_date}</span>}
                  </div>
                  {m.remarks && <p className="text-xs text-gray-500 mt-1 italic">{m.remarks}</p>}
                </div>
              </div>
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
                      data.risk.risk_label === 'High' ? 'bg-red-500' :
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
              {ppmUs > 0 && (
                <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-semibold">
                  {ppmUs} US
                </span>
              )}
            </div>
            {data.ppm_records.length === 0 ? (
              <p className="text-xs text-gray-400">No PPM records</p>
            ) : (
              <div className="space-y-2">
                {data.ppm_records.map((p: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-gray-50 last:border-0">
                    <span className="text-gray-600">Year {p.year} · Cycle {p.cycle}</span>
                    <span className={`font-bold px-2 py-0.5 rounded-full ${
                      p.result === 'US' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                    }`}>
                      {p.result ?? '—'}
                    </span>
                  </div>
                ))}
              </div>
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
    </div>
  )
}
