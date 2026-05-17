'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { RefreshCw, TrendingUp, AlertTriangle } from 'lucide-react'
import RiskBadge from '@/components/RiskBadge'
import RiskChart from '@/components/RiskChart'
import { getPredictions, getRiskDistribution, getDriftReport, retrain } from '@/lib/api'
import { getUser, isAdmin } from '@/lib/auth'
import { getStudents } from '@/lib/api'

export default function RiskPage() {
  const router   = useRouter()
  const user     = getUser()
  const admin    = isAdmin(user)
  const [predictions, setPredictions] = useState<any[]>([])
  const [distribution, setDistribution] = useState<Record<string, number>>({})
  const [drift, setDrift]           = useState<any>(null)
  const [retraining, setRetraining] = useState(false)
  const [sortKey, setSortKey]       = useState<'risk_score' | 'student_name'>('risk_score')
  const [loading, setLoading]       = useState(true)

  async function load() {
    setLoading(true)
    try {
      if (admin) {
        const [preds, dist, dr] = await Promise.all([
          getPredictions(),
          getRiskDistribution(),
          getDriftReport().catch(() => null),
        ])
        setPredictions(preds)
        setDistribution(dist.distribution)
        setDrift(dr)
      } else {
        // Lecturer: filter predictions to their own students
        const [students, preds] = await Promise.all([getStudents(), getPredictions()])
        const myIds = new Set(students.map((s: any) => s.student_id))
        const mine  = preds.filter((p: any) => myIds.has(p.student_id))
        setPredictions(mine)
        const dist: Record<string, number> = {}
        mine.forEach((p: any) => { dist[p.risk_label] = (dist[p.risk_label] || 0) + 1 })
        setDistribution(dist)
      }
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function handleRetrain() {
    setRetraining(true)
    try { await retrain(); await load() }
    catch (e: any) { alert(e.message) }
    finally { setRetraining(false) }
  }

  const sorted = [...predictions].sort((a, b) =>
    sortKey === 'risk_score'
      ? (b.risk_score ?? 0) - (a.risk_score ?? 0)
      : a.student_name.localeCompare(b.student_name)
  )

  return (
    <div className="max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Risk Analysis</h1>
          <p className="text-gray-500 text-sm">ML-powered graduation delay predictions</p>
        </div>
        {admin && (
          <button
            onClick={handleRetrain}
            disabled={retraining}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-semibold rounded-lg transition"
          >
            <RefreshCw className={`w-4 h-4 ${retraining ? 'animate-spin' : ''}`} />
            {retraining ? 'Retraining…' : 'Retrain Model'}
          </button>
        )}
      </div>

      {/* Top row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pie chart */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            <h2 className="font-semibold text-gray-800">Risk Distribution</h2>
          </div>
          {loading ? (
            <div className="h-48 flex items-center justify-center text-gray-400">Loading…</div>
          ) : (
            <RiskChart distribution={distribution} />
          )}
        </div>

        {/* Summary */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Summary</h2>
          {(['High', 'Medium', 'Low'] as const).map(label => {
            const count = distribution[label] ?? 0
            const total = Object.values(distribution).reduce((a, b) => a + b, 0)
            const pct   = total > 0 ? Math.round(count / total * 100) : 0
            const bg    = label === 'High' ? 'bg-red-500' : label === 'Medium' ? 'bg-amber-500' : 'bg-green-500'
            return (
              <div key={label}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600">{label} Risk</span>
                  <span className="font-semibold">{count} ({pct}%)</span>
                </div>
                <div className="bg-gray-100 rounded-full h-2">
                  <div className={`${bg} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
          <p className="text-xs text-gray-400 pt-2">Total: {Object.values(distribution).reduce((a, b) => a + b, 0)} students</p>
        </div>

        {/* Drift report (admin only) */}
        {admin && (
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-4 h-4 text-indigo-600" />
              <h2 className="font-semibold text-gray-800">Data Drift Report</h2>
            </div>
            {drift ? (
              <div className="space-y-3">
                <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold ${
                  drift.dataset_drift ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
                }`}>
                  {drift.dataset_drift ? '⚠️ Drift Detected' : '✅ No Significant Drift'}
                </div>
                <div className="text-sm text-gray-600 space-y-1">
                  <p>Drifted features: <strong>{drift.drifted_features} / {drift.total_features}</strong></p>
                  <p>Drift share: <strong>{(drift.drift_share * 100).toFixed(1)}%</strong></p>
                  <p>Alert threshold: {(drift.threshold * 100).toFixed(0)}%</p>
                </div>
                <p className="text-xs text-gray-400">Last checked: {drift.created_at?.slice(0, 16)}</p>
              </div>
            ) : (
              <p className="text-sm text-gray-400">Run the model first to see drift data.</p>
            )}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Student Risk Scores</h2>
          <select
            value={sortKey}
            onChange={e => setSortKey(e.target.value as any)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none"
          >
            <option value="risk_score">Sort by Risk Score</option>
            <option value="student_name">Sort by Name</option>
          </select>
        </div>

        {loading ? (
          <div className="py-16 text-center text-gray-400">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wide text-left">
                  <th className="px-4 py-3">Student</th>
                  <th className="px-4 py-3">Program</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3">Score</th>
                  <th className="px-4 py-3">Top Risk Factor</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {sorted.map(p => (
                  <tr key={p.student_id} className="hover:bg-gray-50/50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{p.student_name}</p>
                      <p className="text-xs text-gray-400">{p.student_id_number}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{p.degree_type} · {p.study_method}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <RiskBadge label={p.risk_label} />
                        {p.prediction_stage === 1 && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-600 border border-blue-100 w-fit">
                            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                            Early Prediction
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-semibold text-gray-700">{p.risk_score?.toFixed(1)}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {p.key_risk_factors?.[0] ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => router.push(`/students/${p.student_id}`)}
                        className="text-xs text-indigo-600 hover:underline"
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
