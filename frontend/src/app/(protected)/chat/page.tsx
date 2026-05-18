'use client'
import { useEffect, useRef, useState } from 'react'
import { Send, Bot, User, RefreshCw, ChevronDown } from 'lucide-react'
import { getToken } from '@/lib/auth'
import { wsUrl } from '@/lib/api'
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line,
} from 'recharts'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── Types ─────────────────────────────────────────────────────────────────────
type Role = 'user' | 'assistant' | 'system'

interface ChartSpec {
  type: 'pie' | 'bar' | 'line' | 'stacked_bar'
  title: string
  data?: { name: string; value: number }[]
  categories?: string[]
  values?: number[]
  series?: { name: string; data: number[]; color?: string }[]
  colors?: string[]
}

interface Message {
  id: number
  role: Role
  content: string
  charts?: ChartSpec[]
  timestamp?: string
}

interface Step { type: string; content: string }

const DEFAULT_COLORS = [
  '#6366f1','#22c55e','#f59e0b','#ef4444',
  '#0ea5e9','#a855f7','#ec4899','#14b8a6',
]

// ── Chart component ────────────────────────────────────────────────────────────
function InlineChart({ spec }: { spec: ChartSpec }) {
  const colors = spec.colors ?? DEFAULT_COLORS

  if (spec.type === 'pie' && spec.data) {
    return (
      <div className="w-full">
        <p className="text-xs font-semibold text-gray-500 mb-2 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie data={spec.data} dataKey="value" nameKey="name"
              cx="50%" cy="50%" outerRadius={100}
              label={({ name, percent }) => percent > 0.05 ? `${(percent * 100).toFixed(0)}%` : ''}
              labelLine={false}
            >
              {spec.data.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
            </Pie>
            <Tooltip formatter={(v: number) => [v, '']} />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.type === 'bar' && spec.categories && spec.values) {
    const data = spec.categories.map((c, i) => ({ name: c, value: spec.values![i] }))
    return (
      <div className="w-full">
        <p className="text-xs font-semibold text-gray-500 mb-2 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 4, right: 12, bottom: 50, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.type === 'stacked_bar' && spec.categories && spec.series) {
    const data = spec.categories.map((c, i) => {
      const row: Record<string, string | number> = { name: c }
      spec.series!.forEach(s => { row[s.name] = s.data[i] ?? 0 })
      return row
    })
    return (
      <div className="w-full">
        <p className="text-xs font-semibold text-gray-500 mb-2 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 4, right: 12, bottom: 50, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
            {spec.series.map((s, i) => (
              <Bar key={s.name} dataKey={s.name} stackId="a"
                fill={s.color ?? colors[i % colors.length]}
                radius={i === spec.series!.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.type === 'line' && spec.categories && spec.values) {
    const data = spec.categories.map((c, i) => ({ name: c, value: spec.values![i] }))
    return (
      <div className="w-full">
        <p className="text-xs font-semibold text-gray-500 mb-2 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 4, right: 12, bottom: 50, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-35} textAnchor="end"
              interval={Math.floor(data.length / 8)} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke={colors[0]} dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return <p className="text-xs text-gray-400">Unsupported chart: {spec.type}</p>
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'assistant', content: "Hello! I'm your AI Assistant. Ask me anything about students, milestones, risk predictions, or deadlines — or ask me to show data as a chart!" },
  ])
  const [steps, setSteps]         = useState<Step[]>([])
  const [input, setInput]         = useState('')
  const [thinking, setThinking]   = useState(false)
  const [showSteps, setShowSteps] = useState(false)
  const [connected, setConnected] = useState(false)
  const [model, setModel]         = useState<'local' | 'external'>('local')

  const ws    = useRef<WebSocket | null>(null)
  const end   = useRef<HTMLDivElement>(null)
  const idRef = useRef(1)

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, thinking])
  useEffect(() => { connect(); return () => ws.current?.close() }, [])

  function handleModelSwitch(m: 'local' | 'external') {
    if (m === model) return
    setModel(m)
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'switch_model', model: m }))
    }
  }

  function connect() {
    const token = getToken()
    if (!token) return
    const socket = new WebSocket(wsUrl())
    ws.current = socket

    socket.onopen = () => socket.send(JSON.stringify({ token, model }))

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.type === 'auth_success')  { setConnected(true); return }
      if (data.type === 'model_switched') {
        setModel(data.model === 'external' ? 'external' : 'local')
        return
      }
      if (data.type === 'thinking')     { setThinking(true); setSteps([]); return }

      if (['agent_thinking', 'tool_call', 'tool_result'].includes(data.type)) {
        setSteps(prev => [...prev, { type: data.type, content: data.content || data.tool || '' }])
        return
      }

      if (data.type === 'chart_action') {
        setThinking(false)
        try {
          const payload = JSON.parse(data.message)
          setMessages(prev => [...prev, {
            id: idRef.current++, role: 'assistant', content: '', charts: payload.charts,
          }])
        } catch { /* ignore */ }
        return
      }

      if (data.type === 'nav_action') {
        setThinking(false)
        try {
          const payload = JSON.parse(data.message)
          setMessages(prev => [...prev, {
            id: idRef.current++, role: 'assistant',
            content: `Navigating to ${payload.page}…`,
          }])
          setTimeout(() => { window.location.href = payload.url }, 800)
        } catch { /* ignore */ }
        return
      }

      if (data.type === 'push_alert') {
        const alerts = data.alerts as Array<{ level: string; message: string }>
        if (alerts?.length > 0) {
          const summary = '🔔 System Alert\n' + alerts.map(a =>
            `${a.level === 'high' ? '🔴' : a.level === 'warning' ? '🟡' : 'ℹ️'} ${a.message}`
          ).join('\n')
          setMessages(prev => [...prev, { id: idRef.current++, role: 'system', content: summary }])
        }
        return
      }

      if (data.type === 'message') {
        setThinking(false)
        setMessages(prev => [...prev, {
          id: idRef.current++, role: 'assistant',
          content: data.message, timestamp: data.timestamp,
        }])
        return
      }

      if (data.type === 'error') {
        setThinking(false)
        setMessages(prev => [...prev, {
          id: idRef.current++, role: 'system', content: `⚠️ ${data.message}`,
        }])
      }
    }

    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
  }

  function handleSend() {
    const msg = input.trim()
    if (!msg || ws.current?.readyState !== WebSocket.OPEN) return
    setMessages(prev => [...prev, { id: idRef.current++, role: 'user', content: msg }])
    ws.current.send(JSON.stringify({ message: msg }))
    setInput('')
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const stepLabel: Record<string, string> = {
    agent_thinking: '🤔 Thinking',
    tool_call:      '🔧 Tool call',
    tool_result:    '📊 Result',
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] max-w-4xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Assistant</h1>
          <p className="text-gray-500 text-sm flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-gray-400'}`} />
            {connected ? 'Connected' : 'Connecting…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Model toggle */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
            {(['local', 'external'] as const).map(m => (
              <button
                key={m}
                onClick={() => handleModelSwitch(m)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition ${
                  model === m
                    ? 'bg-white shadow text-indigo-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {m === 'local' ? 'Local' : 'MiMo'}
              </button>
            ))}
          </div>

          {steps.length > 0 && (
            <button onClick={() => setShowSteps(v => !v)}
              className="flex items-center gap-1 text-xs text-indigo-600 border border-indigo-200 rounded-lg px-3 py-1.5 hover:bg-indigo-50">
              Agent steps ({steps.length})
              <ChevronDown className={`w-3 h-3 transition-transform ${showSteps ? 'rotate-180' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Steps panel */}
      {showSteps && steps.length > 0 && (
        <div className="bg-gray-900 text-gray-300 rounded-xl p-4 mb-3 text-xs font-mono space-y-1 max-h-40 overflow-y-auto">
          {steps.map((s, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-indigo-400 flex-shrink-0">{stepLabel[s.type] ?? s.type}</span>
              <span className="truncate">{s.content}</span>
            </div>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map(m => {
          const isUser   = m.role === 'user'
          const isSystem = m.role === 'system'
          const hasCharts = m.charts && m.charts.length > 0

          return (
            <div key={m.id} className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                isUser ? 'bg-indigo-600' : isSystem ? 'bg-red-100' : 'bg-gray-100'
              }`}>
                {isUser
                  ? <User className="w-4 h-4 text-white" />
                  : <Bot className={`w-4 h-4 ${isSystem ? 'text-red-500' : 'text-gray-600'}`} />
                }
              </div>

              <div className={`flex flex-col gap-2 ${isUser ? 'items-end' : 'items-start'} max-w-[75%]`}>
                {/* Text bubble */}
                {m.content && (
                  <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    isUser
                      ? 'bg-indigo-600 text-white rounded-tr-sm whitespace-pre-wrap'
                      : isSystem
                      ? 'bg-red-50 text-red-800 border border-red-100 whitespace-pre-wrap'
                      : 'bg-white border border-gray-100 shadow-sm text-gray-800 rounded-tl-sm'
                  }`}>
                    {isUser || isSystem ? m.content : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: (p) => <table className="text-xs border-collapse w-full my-2" {...p} />,
                          thead: (p) => <thead className="bg-gray-50" {...p} />,
                          th: (p) => <th className="border border-gray-200 px-2 py-1 text-left font-semibold" {...p} />,
                          td: (p) => <td className="border border-gray-200 px-2 py-1" {...p} />,
                          p:  (p) => <p className="mb-1 last:mb-0" {...p} />,
                          ul: (p) => <ul className="list-disc pl-4 mb-1 space-y-0.5" {...p} />,
                          ol: (p) => <ol className="list-decimal pl-4 mb-1 space-y-0.5" {...p} />,
                          li: (p) => <li className="leading-snug" {...p} />,
                          strong: (p) => <strong className="font-semibold" {...p} />,
                          code: (p) => <code className="bg-gray-100 rounded px-1 text-xs font-mono" {...p} />,
                          pre: (p) => <pre className="bg-gray-100 rounded p-2 text-xs overflow-x-auto my-1" {...p} />,
                        }}
                      >
                        {m.content}
                      </ReactMarkdown>
                    )}
                  </div>
                )}

                {/* Charts */}
                {hasCharts && (
                  <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm p-4 w-[480px] flex flex-col gap-6">
                    {m.charts!.map((spec, i) => <InlineChart key={i} spec={spec} />)}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Thinking indicator */}
        {thinking && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-gray-600 animate-pulse" />
            </div>
            <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                {[0, 150, 300].map(d => (
                  <span key={d} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={end} />
      </div>

      {/* Input */}
      <div className="mt-4">
        {!connected && (
          <div className="text-center mb-2">
            <button onClick={connect}
              className="flex items-center gap-2 mx-auto text-sm text-indigo-600 hover:underline">
              <RefreshCw className="w-4 h-4" /> Reconnect
            </button>
          </div>
        )}
        <div className="flex gap-3 bg-white border border-gray-200 rounded-2xl p-2 shadow-sm">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about students, risks, deadlines — or say 'show risk distribution as pie'…"
            rows={1}
            className="flex-1 resize-none px-3 py-2 text-sm focus:outline-none bg-transparent"
          />
          <button onClick={handleSend}
            disabled={!input.trim() || !connected}
            className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-200 text-white rounded-xl transition">
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-2">Press Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}
