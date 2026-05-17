'use client'
import { useEffect, useMemo, useState, useCallback } from 'react'
import dynamic from 'next/dynamic'
import {
  Filter, Download, X, Settings2, Maximize2, Minimize2,
  RefreshCw, ChevronUp, ChevronDown, Eye, EyeOff, RotateCcw,
} from 'lucide-react'
import { getAnalyticsData, getMilestoneMatrix, getSupervisors } from '@/lib/api'
import { getUser, isAdmin } from '@/lib/auth'

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false })

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────
interface Student {
  student_id: number; student_name: string; student_id_number: string
  degree_type: string; study_method: string; gender: string | null
  enrollment_year: number; faculty: string; program: string
  country: string | null; funding: string | null
  risk_score: number | null; risk_label: string | null
  key_risk_factors: string[]
  rpd_delay_days: number; ppm_us_count: number; ppm_total: number
  is_cross_discipline: boolean; in_research_group: boolean
  weekly_work_hours: number; family_support: number | null
  supervisor_id: number | null; supervisor_name: string | null
}

type Size = 'third' | 'half' | 'full'
interface ChartCfg { id: string; visible: boolean; size: Size; order: number }

interface Filters {
  faculty: string | null
  degreeType: string | null
  studyMethod: string | null
  riskLabel: string | null
  enrollYear: number | null
  supervisorId: number | null
}

// ─────────────────────────────────────────────────────────────
// Chart definitions (static metadata)
// ─────────────────────────────────────────────────────────────
const CHART_DEFS = [
  { id: 'risk-faculty', title: 'Risk Distribution by Faculty',       defaultSize: 'half'  as Size },
  { id: 'scatter',      title: 'Risk Score vs RPD Delay (Scatter)',  defaultSize: 'half'  as Size },
  { id: 'factors',      title: 'Top Risk Factors',                   defaultSize: 'half'  as Size },
  { id: 'milestone',    title: 'Milestone Completion by Type',       defaultSize: 'full'  as Size },
  { id: 'enrollment',   title: 'Enrollment by Year',                 defaultSize: 'third' as Size },
  { id: 'degree',       title: 'Degree Type',                        defaultSize: 'third' as Size },
  { id: 'mode',         title: 'Study Mode',                         defaultSize: 'third' as Size },
  { id: 'gender',       title: 'Gender Distribution',               defaultSize: 'third' as Size },
  { id: 'country',      title: 'Students by Country',               defaultSize: 'third' as Size },
]

const DEFAULT_CFGS: ChartCfg[] = CHART_DEFS.map((d, i) => ({
  id: d.id, visible: true, size: d.defaultSize, order: i,
}))

const LS_KEY = 'datatrain_chart_layout'

function loadCfgs(): ChartCfg[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return DEFAULT_CFGS
    const saved: ChartCfg[] = JSON.parse(raw)
    // merge saved with defaults in case new charts were added
    const savedMap = Object.fromEntries(saved.map(c => [c.id, c]))
    return CHART_DEFS.map((d, i) => savedMap[d.id] ?? { id: d.id, visible: true, size: d.defaultSize, order: i })
  } catch { return DEFAULT_CFGS }
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
const RISK_COLORS: Record<string, string> = { High: '#dc2626', Medium: '#d97706', Low: '#16a34a' }
const PALETTE = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444','#14b8a6','#f97316']

function countBy<T>(arr: T[], key: (x: T) => string | null): Record<string, number> {
  const m: Record<string, number> = {}
  arr.forEach(x => { const k = key(x); if (k) m[k] = (m[k] || 0) + 1 })
  return m
}
function avg(ns: number[]) { return ns.length ? ns.reduce((a, b) => a + b) / ns.length : 0 }

const SIZE_COLS: Record<Size, string> = {
  third: 'col-span-6 xl:col-span-2',
  half:  'col-span-6 xl:col-span-3',
  full:  'col-span-6',
}
const SIZE_LABELS: Record<Size, string> = { third: '⅓', half: '½', full: '■' }

// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────
function Pill({ label, active, onClick }: { label: string; active: boolean; onClick(): void }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs font-semibold border transition ${
        active ? 'bg-indigo-600 text-white border-indigo-600'
               : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
      }`}
    >{label}</button>
  )
}

function KPI({ label, value, sub, color = 'indigo' }: { label: string; value: string | number; sub?: string; color?: string }) {
  const c: Record<string, string> = {
    indigo: 'text-indigo-700', red: 'text-red-600', amber: 'text-amber-600', green: 'text-green-600',
  }
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${c[color] ?? c.indigo}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

// Chart card with expand button
function ChartCard({
  title, children, onExpand,
}: { title: string; children: React.ReactNode; onExpand(): void }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <button onClick={onExpand} title="Focus"
          className="text-gray-300 hover:text-indigo-500 transition">
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  )
}

// Expand modal
function ExpandModal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose(): void }) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', fn)
    return () => window.removeEventListener('keydown', fn)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">{title}</h2>
          <button onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100">
            <Minimize2 className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 p-6">{children}</div>
      </div>
    </div>
  )
}

// Customize drawer
function CustomizeDrawer({
  cfgs, onClose, onChange, onReset,
}: {
  cfgs: ChartCfg[]
  onClose(): void
  onChange(cfgs: ChartCfg[]): void
  onReset(): void
}) {
  const sorted = [...cfgs].sort((a, b) => a.order - b.order)

  function toggle(id: string) {
    onChange(cfgs.map(c => c.id === id ? { ...c, visible: !c.visible } : c))
  }
  function setSize(id: string, size: Size) {
    onChange(cfgs.map(c => c.id === id ? { ...c, size } : c))
  }
  function move(id: string, dir: -1 | 1) {
    const list = [...sorted]
    const idx  = list.findIndex(c => c.id === id)
    const swap = idx + dir
    if (swap < 0 || swap >= list.length) return
    const next = list.map((c, i) => {
      if (i === idx)  return { ...c, order: list[swap].order }
      if (i === swap) return { ...c, order: list[idx].order }
      return c
    })
    onChange(next)
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative bg-white w-80 h-full shadow-2xl flex flex-col z-50">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-indigo-600" />
            <span className="font-semibold text-gray-800">Customize Dashboard</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="px-5 py-2 text-xs text-gray-400">
          Toggle charts on/off, change size, or reorder.
        </p>

        {/* Chart list */}
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
          {sorted.map((cfg, i) => {
            const def = CHART_DEFS.find(d => d.id === cfg.id)!
            return (
              <div key={cfg.id}
                className={`rounded-xl border p-3 transition ${
                  cfg.visible ? 'border-gray-200 bg-white' : 'border-dashed border-gray-200 bg-gray-50 opacity-60'
                }`}
              >
                {/* Title + toggle */}
                <div className="flex items-center gap-2 mb-2">
                  <button onClick={() => toggle(cfg.id)}
                    className={`flex-shrink-0 transition ${cfg.visible ? 'text-indigo-500' : 'text-gray-300'}`}>
                    {cfg.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  </button>
                  <span className="text-xs font-medium text-gray-700 flex-1 leading-snug">{def.title}</span>
                </div>

                {/* Size + reorder */}
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    {(['third', 'half', 'full'] as Size[]).map(s => (
                      <button key={s} onClick={() => setSize(cfg.id, s)}
                        className={`px-2 py-0.5 text-xs rounded-md font-mono font-semibold border transition ${
                          cfg.size === s
                            ? 'bg-indigo-600 text-white border-indigo-600'
                            : 'bg-white text-gray-500 border-gray-200 hover:border-indigo-300'
                        }`}
                      >{SIZE_LABELS[s]}</button>
                    ))}
                  </div>
                  <div className="ml-auto flex gap-1">
                    <button onClick={() => move(cfg.id, -1)} disabled={i === 0}
                      className="p-1 rounded text-gray-400 hover:text-gray-700 disabled:opacity-20">
                      <ChevronUp className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => move(cfg.id, 1)} disabled={i === sorted.length - 1}
                      className="p-1 rounded text-gray-400 hover:text-gray-700 disabled:opacity-20">
                      <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-100">
          <button onClick={onReset}
            className="w-full flex items-center justify-center gap-2 py-2 text-sm text-gray-500 hover:text-red-500 border border-dashed border-gray-200 rounded-lg transition">
            <RotateCcw className="w-3.5 h-3.5" /> Reset to defaults
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const user    = getUser()
  const admin   = isAdmin(user)

  const [raw, setRaw]           = useState<Student[]>([])
  const [milestones, setMilestones] = useState<any[]>([])
  const [supervisors, setSupervisors] = useState<any[]>([])
  const [loading, setLoading]   = useState(true)

  const [filters, setFilters] = useState<Filters>({
    faculty: null, degreeType: null, studyMethod: null,
    riskLabel: null, enrollYear: null, supervisorId: null,
  })

  const [cfgs, setCfgs]           = useState<ChartCfg[]>(DEFAULT_CFGS)
  const [showCustomize, setShowCustomize] = useState(false)
  const [expandedId, setExpandedId]       = useState<string | null>(null)

  // Load chart config from localStorage
  useEffect(() => { setCfgs(loadCfgs()) }, [])

  // Persist chart config to localStorage
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(cfgs)) } catch {}
  }, [cfgs])

  // Fetch data
  useEffect(() => {
    const p = [getAnalyticsData(), getMilestoneMatrix()]
    const q = admin ? [...p, getSupervisors()] : p
    Promise.all(q)
      .then(([d, m, s]: any[]) => {
        setRaw(d.students)
        setMilestones(m)
        if (s) setSupervisors(s)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [admin])

  // ── Filtering ──────────────────────────────────────────────
  const data = useMemo(() => raw.filter(s =>
    (!filters.faculty      || s.faculty      === filters.faculty) &&
    (!filters.degreeType   || s.degree_type  === filters.degreeType) &&
    (!filters.studyMethod  || s.study_method === filters.studyMethod) &&
    (!filters.riskLabel    || s.risk_label   === filters.riskLabel) &&
    (!filters.enrollYear   || s.enrollment_year === filters.enrollYear) &&
    (!filters.supervisorId || s.supervisor_id === filters.supervisorId)
  ), [raw, filters])

  function setF<K extends keyof Filters>(key: K, val: Filters[K]) {
    setFilters(prev => ({ ...prev, [key]: prev[key] === val ? null : val }))
  }
  function clearFilters() {
    setFilters({ faculty: null, degreeType: null, studyMethod: null,
                 riskLabel: null, enrollYear: null, supervisorId: null })
  }
  const hasFilter = Object.values(filters).some(v => v !== null)

  const faculties = Array.from(new Set(raw.map(s => s.faculty))).sort()
  const years     = Array.from(new Set(raw.map(s => s.enrollment_year))).sort()

  // ── KPIs ───────────────────────────────────────────────────
  const total      = data.length
  const highRisk   = data.filter(s => s.risk_label === 'High').length
  const avgScore   = avg(data.filter(s => s.risk_score != null).map(s => s.risk_score!))
  const overduePct = total ? Math.round(data.filter(s => s.rpd_delay_days > 0).length / total * 100) : 0

  // ── EChart options (all memoised) ──────────────────────────

  // 1. Risk stacked bar by faculty
  const riskByFaculty = useMemo(() => {
    const map: Record<string, Record<string, number>> = {}
    data.forEach(s => {
      if (!map[s.faculty]) map[s.faculty] = { High: 0, Medium: 0, Low: 0 }
      map[s.faculty][s.risk_label ?? 'Low']++
    })
    const facs = Object.keys(map).sort()
    return { facs, high: facs.map(f => map[f].High || 0), medium: facs.map(f => map[f].Medium || 0), low: facs.map(f => map[f].Low || 0) }
  }, [data])

  const riskFacultyOpt = useMemo(() => ({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend:  { data: ['High','Medium','Low'], bottom: 0, textStyle: { fontSize: 11 } },
    grid:    { left: 10, right: 10, bottom: 36, top: 6, containLabel: true },
    xAxis:   { type: 'value' },
    yAxis:   { type: 'category', data: riskByFaculty.facs,
               axisLabel: { fontSize: 10, formatter: (v: string) => v.length > 28 ? v.slice(0,26)+'…' : v } },
    series: [
      { name:'High',   type:'bar', stack:'r', data: riskByFaculty.high,   itemStyle:{ color:'#dc2626' } },
      { name:'Medium', type:'bar', stack:'r', data: riskByFaculty.medium, itemStyle:{ color:'#d97706' } },
      { name:'Low',    type:'bar', stack:'r', data: riskByFaculty.low,    itemStyle:{ color:'#16a34a' } },
    ],
  }), [riskByFaculty])

  // 2. Scatter: risk score vs RPD delay
  const scatterOpt = useMemo(() => ({
    tooltip: { trigger:'item',
      formatter: (p: any) => `<b>${p.data[2]}</b><br>RPD: ${p.data[0]}d | Score: ${Number(p.data[1]).toFixed(1)}` },
    legend: { data:['High','Medium','Low'], bottom:0, textStyle:{ fontSize:11 } },
    grid:   { left:20, right:10, bottom:36, top:6, containLabel:true },
    xAxis:  { type:'value', name:'RPD Delay (days)', nameLocation:'middle', nameGap:24, splitLine:{ lineStyle:{ type:'dashed' } } },
    yAxis:  { type:'value', name:'Risk Score', nameLocation:'middle', nameGap:32 },
    series: (['High','Medium','Low'] as const).map(label => ({
      name: label, type:'scatter', symbolSize: 10,
      data: data.filter(s => s.risk_label === label).map(s => [s.rpd_delay_days, s.risk_score ?? 0, s.student_name]),
      itemStyle: { color: RISK_COLORS[label], opacity: 0.8 },
    })),
  }), [data])

  // 3. Top risk factors
  const factorsOpt = useMemo(() => {
    const m: Record<string,number> = {}
    data.forEach(s => s.key_risk_factors.forEach(f => { m[f] = (m[f]||0)+1 }))
    const top = Object.entries(m).sort((a,b)=>b[1]-a[1]).slice(0,10)
    return {
      tooltip: { trigger:'axis', axisPointer:{ type:'shadow' } },
      grid:    { left:10, right:30, bottom:6, top:6, containLabel:true },
      xAxis:   { type:'value', minInterval:1 },
      yAxis:   { type:'category', data: top.map(([f])=>f).reverse(),
                 axisLabel:{ fontSize:10, formatter:(v:string)=>v.length>36?v.slice(0,34)+'…':v } },
      series:  [{ type:'bar', data: top.map(([,c])=>c).reverse(),
                  itemStyle:{ color:'#f59e0b', borderRadius:[0,4,4,0] },
                  label:{ show:true, position:'right', fontSize:11 } }],
    }
  }, [data])

  // 4. Milestone stacked bar
  const milestoneOpt = useMemo(() => {
    const myIds = new Set(data.map(s => s.student_id))
    const scope = milestones.filter(m => myIds.has(m.student_id))
    const map: Record<string, Record<string,number>> = {}
    scope.forEach(m => {
      if (!map[m.milestone]) map[m.milestone] = { Completed:0, Pending:0, Overdue:0 }
      const st = (m.status === 'Pending' && m.expected_date && new Date(m.expected_date) < new Date())
        ? 'Overdue' : m.status
      map[m.milestone][st] = (map[m.milestone][st]||0)+1
    })
    const names = Object.keys(map)
    return {
      tooltip: { trigger:'axis', axisPointer:{ type:'shadow' } },
      legend:  { data:['Completed','Pending','Overdue'], bottom:0, textStyle:{ fontSize:11 } },
      grid:    { left:10, right:10, bottom:36, top:6, containLabel:true },
      xAxis:   { type:'category', data: names, axisLabel:{ rotate:15, fontSize:10 } },
      yAxis:   { type:'value', minInterval:1 },
      series: [
        { name:'Completed', type:'bar', stack:'s', data: names.map(n=>map[n].Completed||0), itemStyle:{ color:'#16a34a' } },
        { name:'Pending',   type:'bar', stack:'s', data: names.map(n=>map[n].Pending  ||0), itemStyle:{ color:'#d97706' } },
        { name:'Overdue',   type:'bar', stack:'s', data: names.map(n=>map[n].Overdue  ||0), itemStyle:{ color:'#dc2626' } },
      ],
    }
  }, [data, milestones])

  // 5. Enrollment by year
  const enrollOpt = useMemo(() => {
    const m = countBy(data, s => String(s.enrollment_year))
    const ys = years.map(String)
    return {
      tooltip: { trigger:'axis' },
      grid:    { left:10, right:10, bottom:6, top:6, containLabel:true },
      xAxis:   { type:'category', data: ys },
      yAxis:   { type:'value', minInterval:1 },
      series:  [{ type:'bar', data: ys.map(y=>m[y]||0),
                  itemStyle:{ color:'#6366f1', borderRadius:[4,4,0,0] },
                  label:{ show:true, position:'top', fontSize:11 } }],
    }
  }, [data, years])

  // 6–8. Donut helpers
  function donutOpt(counts: Record<string,number>, colors?: string[]) {
    const entries = Object.entries(counts)
    return {
      tooltip: { trigger:'item', formatter:'{b}: {c} ({d}%)' },
      legend:  { bottom:0, textStyle:{ fontSize:10 } },
      series:  [{ type:'pie', radius:['42%','68%'], center:['50%','44%'],
                  data: entries.map(([name,value],i) => ({
                    name, value,
                    itemStyle:{ color: colors ? colors[i] : PALETTE[i] },
                  })),
                  label:{ show:true, formatter:'{b}\n{d}%', fontSize:10 } }],
    }
  }
  const degreeOpt  = useMemo(() => donutOpt(countBy(data, s=>s.degree_type),  ['#6366f1','#8b5cf6']), [data])
  const modeOpt    = useMemo(() => donutOpt(countBy(data, s=>s.study_method), ['#f59e0b','#10b981']), [data])
  const genderOpt  = useMemo(() => donutOpt(countBy(data, s=>s.gender??'Unknown')), [data])

  // 9. Country horizontal bar
  const countryOpt = useMemo(() => {
    const top = Object.entries(countBy(data, s=>s.country??'Unknown')).sort((a,b)=>b[1]-a[1]).slice(0,8)
    return {
      tooltip: { trigger:'axis', axisPointer:{ type:'shadow' } },
      grid:    { left:10, right:30, bottom:6, top:6, containLabel:true },
      xAxis:   { type:'value', minInterval:1 },
      yAxis:   { type:'category', data: top.map(([c])=>c).reverse(), axisLabel:{ fontSize:10 } },
      series:  [{ type:'bar', data: top.map(([,c])=>c).reverse(),
                  itemStyle:{ color:'#8b5cf6', borderRadius:[0,4,4,0] },
                  label:{ show:true, position:'right', fontSize:11 } }],
    }
  }, [data])

  // Chart option map
  const optMap: Record<string, object> = {
    'risk-faculty': riskFacultyOpt,
    'scatter':      scatterOpt,
    'factors':      factorsOpt,
    'milestone':    milestoneOpt,
    'enrollment':   enrollOpt,
    'degree':       degreeOpt,
    'mode':         modeOpt,
    'gender':       genderOpt,
    'country':      countryOpt,
  }

  // Chart heights (in the card)
  const heightMap: Record<string, number> = {
    'risk-faculty': Math.max(220, riskByFaculty.facs.length * 36 + 50),
    'scatter': 280, 'factors': 280, 'milestone': 260,
    'enrollment': 220, 'degree': 220, 'mode': 220, 'gender': 220, 'country': 220,
  }

  // ── CSV export ─────────────────────────────────────────────
  function exportCSV() {
    const cols = ['Name','ID','Faculty','Program','Degree','Mode','Year','Country',
                  'Supervisor','Risk','Score','RPD Delay (d)','PPM US']
    const rows = data.map(s => [
      s.student_name, s.student_id_number, s.faculty, s.program,
      s.degree_type, s.study_method, s.enrollment_year, s.country??'',
      s.supervisor_name??'', s.risk_label??'', s.risk_score?.toFixed(1)??'',
      s.rpd_delay_days, s.ppm_us_count,
    ])
    const csv = [cols,...rows].map(r=>r.map(String).join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type:'text/csv' }))
    a.download = `datatrain-analytics-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
  }

  // ── Sorted visible charts ──────────────────────────────────
  const orderedCharts = [...cfgs].sort((a,b)=>a.order-b.order).filter(c=>c.visible)

  const echartStyle = { height:'100%', width:'100%' }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin" />
    </div>
  )

  const expandedDef  = expandedId ? CHART_DEFS.find(d=>d.id===expandedId) : null
  const expandedOpt  = expandedId ? optMap[expandedId] : null

  return (
    <div className="space-y-5 max-w-[1400px]">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-gray-500 text-sm">
            Showing <strong>{total}</strong> of <strong>{raw.length}</strong> students
            {hasFilter && <span className="text-indigo-500"> · filtered</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCSV}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg shadow-sm transition">
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button onClick={() => setShowCustomize(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg shadow-sm transition">
            <Settings2 className="w-4 h-4" /> Customize
          </button>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-400 uppercase tracking-wide">
          <Filter className="w-3.5 h-3.5" /> Filters
          {hasFilter && (
            <button onClick={clearFilters}
              className="ml-auto flex items-center gap-1 text-gray-400 hover:text-red-500 normal-case font-normal">
              <X className="w-3.5 h-3.5" /> Clear all
            </button>
          )}
        </div>

        {/* Lecturer filter (admin only) */}
        {admin && supervisors.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 font-medium w-20">Lecturer</span>
            <select
              value={filters.supervisorId ?? ''}
              onChange={e => setFilters(prev => ({
                ...prev,
                supervisorId: e.target.value ? Number(e.target.value) : null,
              }))}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 min-w-[220px]"
            >
              <option value="">All lecturers</option>
              {supervisors.map((s: any) => (
                <option key={s.supervisor_id} value={s.supervisor_id}>
                  {s.name} ({s.student_count} students)
                </option>
              ))}
            </select>
            {filters.supervisorId && (
              <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-1 rounded-full">
                {supervisors.find((s: any) => s.supervisor_id === filters.supervisorId)?.name}
              </span>
            )}
          </div>
        )}

        {/* Pill filters */}
        {[
          { label: 'Faculty',      items: faculties, key: 'faculty'      as const },
          { label: 'Degree',       items: ['PhD','Master'], key: 'degreeType' as const },
          { label: 'Mode',         items: ['Full-time','Part-time'], key: 'studyMethod' as const },
          { label: 'Risk',         items: ['High','Medium','Low'], key: 'riskLabel' as const },
          { label: 'Enrol Year',   items: years.map(String), key: 'enrollYear' as const },
        ].map(({ label, items, key }) => (
          <div key={key} className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 font-medium w-20">{label}</span>
            <div className="flex flex-wrap gap-1.5">
              {items.map(item => (
                <Pill key={item} label={typeof item === 'string' && item.length > 24 ? item.replace('Faculty of ','').slice(0,22) : String(item)}
                  active={String(filters[key]) === String(item)}
                  onClick={() => setF(key, (key === 'enrollYear' ? Number(item) : item) as any)}
                />
              ))}
            </div>
          </div>
        ))}

        {/* Active filter chips */}
        {hasFilter && (
          <div className="flex flex-wrap gap-2 pt-1 border-t border-gray-50">
            <span className="text-xs text-gray-400">Active:</span>
            {filters.supervisorId && (
              <span className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 text-xs px-2 py-0.5 rounded-full">
                Lecturer: {supervisors.find((s:any)=>s.supervisor_id===filters.supervisorId)?.name}
                <button onClick={()=>setF('supervisorId',null)}><X className="w-3 h-3"/></button>
              </span>
            )}
            {(['faculty','degreeType','studyMethod','riskLabel','enrollYear'] as const).map(k =>
              filters[k] !== null && (
                <span key={k} className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 text-xs px-2 py-0.5 rounded-full">
                  {String(filters[k])}
                  <button onClick={()=>setF(k,null as any)}><X className="w-3 h-3"/></button>
                </span>
              )
            )}
          </div>
        )}
      </div>

      {/* ── KPIs ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPI label="Students" value={total} />
        <KPI label="High Risk" value={`${highRisk} (${total?Math.round(highRisk/total*100):0}%)`} color="red" />
        <KPI label="Avg Risk Score" value={avgScore.toFixed(1)} sub="out of 100" color="amber" />
        <KPI label="RPD Overdue" value={`${overduePct}%`} sub="of students delayed" color="indigo" />
      </div>

      {/* ── Charts grid (6-col) ── */}
      {orderedCharts.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-200 p-16 text-center">
          <p className="text-gray-400 text-sm">All charts are hidden.</p>
          <button onClick={() => setShowCustomize(true)}
            className="mt-3 text-sm text-indigo-600 hover:underline">
            Open Customize to show charts →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-6 gap-5">
          {orderedCharts.map(cfg => {
            const def = CHART_DEFS.find(d => d.id === cfg.id)!
            const opt = optMap[cfg.id]
            const h   = heightMap[cfg.id] ?? 260
            return (
              <div key={cfg.id} className={SIZE_COLS[cfg.size]}>
                <ChartCard title={def.title} onExpand={() => setExpandedId(cfg.id)}>
                  <div style={{ height: h }}>
                    {opt && <ReactECharts option={opt} style={echartStyle} notMerge />}
                  </div>
                </ChartCard>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Data table ── */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">Data Table</h3>
          <span className="text-xs text-gray-400">{total} rows · reflects active filters</span>
        </div>
        <div className="overflow-x-auto max-h-72">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-50 z-10">
              <tr className="text-left text-gray-500 uppercase tracking-wide font-semibold">
                {['Student','ID','Faculty','Degree','Mode','Year','Lecturer','Risk','Score','RPD Delay'].map(h=>(
                  <th key={h} className="px-3 py-2 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {data.map(s => (
                <tr key={s.student_id} className="hover:bg-gray-50/60">
                  <td className="px-3 py-2 font-medium whitespace-nowrap">{s.student_name}</td>
                  <td className="px-3 py-2 text-gray-400 font-mono">{s.student_id_number}</td>
                  <td className="px-3 py-2 text-gray-500 max-w-[150px] truncate">{s.faculty}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${s.degree_type==='PhD'?'bg-purple-100 text-purple-700':'bg-blue-100 text-blue-700'}`}>
                      {s.degree_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500">{s.study_method}</td>
                  <td className="px-3 py-2 text-gray-500">{s.enrollment_year}</td>
                  <td className="px-3 py-2 text-gray-500 max-w-[120px] truncate">{s.supervisor_name??'—'}</td>
                  <td className="px-3 py-2">
                    {s.risk_label && (
                      <span className="font-semibold" style={{ color: RISK_COLORS[s.risk_label] }}>
                        {s.risk_label}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-semibold text-gray-700">{s.risk_score?.toFixed(1)??'—'}</td>
                  <td className="px-3 py-2">
                    <span className={s.rpd_delay_days>0?'text-red-600 font-semibold':'text-gray-400'}>
                      {s.rpd_delay_days>0?`+${s.rpd_delay_days}d`:`${s.rpd_delay_days}d`}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Customize drawer ── */}
      {showCustomize && (
        <CustomizeDrawer
          cfgs={cfgs}
          onClose={() => setShowCustomize(false)}
          onChange={setCfgs}
          onReset={() => { setCfgs(DEFAULT_CFGS); localStorage.removeItem(LS_KEY) }}
        />
      )}

      {/* ── Expand modal ── */}
      {expandedId && expandedDef && expandedOpt && (
        <ExpandModal title={expandedDef.title} onClose={() => setExpandedId(null)}>
          <ReactECharts option={expandedOpt} style={echartStyle} notMerge />
        </ExpandModal>
      )}
    </div>
  )
}
