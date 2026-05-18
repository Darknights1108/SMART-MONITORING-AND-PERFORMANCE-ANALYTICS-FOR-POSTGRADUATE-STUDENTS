'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import Link from 'next/link'
import {
  Bot, X, Send, User, Minimize2, Maximize2,
  RefreshCw, ExternalLink, ChevronDown, PlusCircle,
} from 'lucide-react'
import { getToken } from '@/lib/auth'
import { wsUrl } from '@/lib/api'
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line,
} from 'recharts'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── Types ──────────────────────────────────────────────────────────────────────
type Role = 'user' | 'assistant' | 'system'

interface ChartSpec {
  type: 'pie' | 'bar' | 'line' | 'stacked_bar'
  title: string
  data?: { name: string; value: number }[]          // pie
  categories?: string[]                              // bar / line / stacked_bar
  values?: number[]                                  // bar / line
  series?: { name: string; data: number[]; color?: string }[]  // stacked_bar
  colors?: string[]
}

interface ChartPayload {
  __chart_action__: true
  charts: ChartSpec[]
}

interface Message {
  id: number
  role: Role
  content: string
  charts?: ChartSpec[]   // present when this is a chart message
}

// ── Default colours ────────────────────────────────────────────────────────────
const DEFAULT_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444',
  '#0ea5e9', '#a855f7', '#ec4899', '#14b8a6',
]

const INITIAL: Message[] = [
  { id: 0, role: 'assistant', content: "Hi! I'm your AI Assistant. Ask me about students, risks, or deadlines — or ask me to show data as a chart!" },
]

const WIDGET_STORAGE_KEY = 'pms-chat-widget-messages-v1'

function getInitialMessages(): Message[] {
  return INITIAL.map(m => ({ ...m }))
}

function loadStoredMessages(): Message[] {
  if (typeof window === 'undefined') return getInitialMessages()
  try {
    const raw = window.localStorage.getItem(WIDGET_STORAGE_KEY)
    if (!raw) return getInitialMessages()
    const parsed = JSON.parse(raw) as Message[]
    if (!Array.isArray(parsed) || parsed.length === 0) return getInitialMessages()
    return parsed
  } catch {
    return getInitialMessages()
  }
}

function nextMsgId(messages: Message[]): number {
  return messages.reduce((max, m) => Math.max(max, Number(m.id) || 0), 0) + 1
}

// ── Chart renderer ─────────────────────────────────────────────────────────────
function NoData({ title }: { title: string }) {
  return (
    <div className="w-full text-center py-4">
      <p className="text-[10px] font-semibold text-gray-500 mb-2 uppercase tracking-wide">{title}</p>
      <p className="text-[11px] text-gray-400 italic">No data available</p>
    </div>
  )
}

function InlineChart({ spec }: { spec: ChartSpec }) {
  const colors = spec.colors ?? DEFAULT_COLORS

  if (spec.type === 'pie') {
    if (!spec.data || spec.data.length === 0) return <NoData title={spec.title} />
    return (
      <div className="w-full">
        <p className="text-[10px] font-semibold text-gray-500 mb-1 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={spec.data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="45%"
              outerRadius={70}
              label={({ percent }) =>
                percent > 0.05 ? `${(percent * 100).toFixed(0)}%` : ''
              }
              labelLine={false}
            >
              {spec.data.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v: number, name: string) => [v, name]} />
            <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.type === 'bar') {
    if (!spec.categories || spec.categories.length === 0) return <NoData title={spec.title} />
    const data = spec.categories.map((c, i) => ({ name: c, value: spec.values![i] }))
    return (
      <div className="w-full">
        <p className="text-[10px] font-semibold text-gray-500 mb-1 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 40, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 9 }}
              angle={-35}
              textAnchor="end"
              interval={0}
            />
            <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
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
        <p className="text-[10px] font-semibold text-gray-500 mb-1 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 40, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 9 }}
              angle={-35}
              textAnchor="end"
              interval={0}
            />
            <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
            <Tooltip />
            <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
            {spec.series.map((s, i) => (
              <Bar key={s.name} dataKey={s.name} stackId="a"
                fill={s.color ?? colors[i % colors.length]}
                radius={i === spec.series!.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.type === 'line') {
    if (!spec.categories || spec.categories.length === 0) return <NoData title={spec.title} />
    const data = spec.categories.map((c, i) => ({ name: c, value: spec.values![i] }))
    return (
      <div className="w-full">
        <p className="text-[10px] font-semibold text-gray-500 mb-1 text-center uppercase tracking-wide">
          {spec.title}
        </p>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 40, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 9 }}
              angle={-35}
              textAnchor="end"
              interval={Math.floor(data.length / 6)}
            />
            <YAxis tick={{ fontSize: 9 }} allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke={colors[0]}
              dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return <p className="text-[10px] text-gray-400">Unsupported chart type: {spec.type}</p>
}

// ── Chat bubble with optional charts ──────────────────────────────────────────
function MessageBubble({ m, isExpanded }: { m: Message; isExpanded: boolean }) {
  const isUser   = m.role === 'user'
  const isSystem = m.role === 'system'
  const hasCharts = m.charts && m.charts.length > 0
  // Chart messages get full-width; text messages are capped
  const bubbleW  = hasCharts ? 'w-full' : isExpanded ? 'max-w-[90%]' : 'max-w-[85%]'

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
        isUser   ? 'bg-indigo-600' :
        isSystem ? 'bg-red-100' : 'bg-white border border-gray-200'
      }`}>
        {isUser
          ? <User className="w-3 h-3 text-white" />
          : <Bot className={`w-3 h-3 ${isSystem ? 'text-red-500' : 'text-indigo-600'}`} />
        }
      </div>

      {/* Bubble */}
      <div className={`${bubbleW} flex flex-col gap-2 min-w-0`}>
        {/* Text content (skip if empty for chart-only messages) */}
        {m.content && (
          <div className={`rounded-2xl px-3 py-2 text-xs leading-relaxed ${
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
                  table: (p) => <table className="text-[10px] border-collapse w-full my-1.5" {...p} />,
                  thead: (p) => <thead className="bg-gray-50" {...p} />,
                  th: (p) => <th className="border border-gray-200 px-1.5 py-0.5 text-left font-semibold" {...p} />,
                  td: (p) => <td className="border border-gray-200 px-1.5 py-0.5" {...p} />,
                  p:  (p) => <p className="mb-1 last:mb-0" {...p} />,
                  ul: (p) => <ul className="list-disc pl-3 mb-1 space-y-0.5" {...p} />,
                  ol: (p) => <ol className="list-decimal pl-3 mb-1 space-y-0.5" {...p} />,
                  li: (p) => <li className="leading-snug" {...p} />,
                  strong: (p) => <strong className="font-semibold" {...p} />,
                  code: (p) => <code className="bg-gray-100 rounded px-0.5 font-mono" {...p} />,
                }}
              >
                {m.content}
              </ReactMarkdown>
            )}
          </div>
        )}

        {/* Charts */}
        {hasCharts && (
          <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm p-3 flex flex-col gap-4">
            {m.charts!.map((spec, i) => (
              <InlineChart key={i} spec={spec} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main widget ────────────────────────────────────────────────────────────────
export default function ChatWidget() {
  const [open, setOpen]           = useState(false)
  const [expanded, setExpanded]   = useState(false)
  const [messages, setMessages]   = useState<Message[]>(getInitialMessages)
  const [input, setInput]         = useState('')
  const [thinking, setThinking]   = useState(false)
  const [connected, setConnected] = useState(false)
  const [unread, setUnread]       = useState(0)
  const [model, setModel]         = useState<'local' | 'external'>('local')
  const [storageReady, setStorageReady] = useState(false)

  const ws     = useRef<WebSocket | null>(null)
  const endRef  = useRef<HTMLDivElement>(null)
  const idRef   = useRef(nextMsgId(messages))
  const openRef = useRef(open)
  openRef.current = open

  // ── WebSocket ────────────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    const token = getToken()
    if (!token) return
    if (ws.current?.readyState === WebSocket.OPEN) return

    const socket = new WebSocket(wsUrl())
    ws.current = socket

    socket.onopen = () => socket.send(JSON.stringify({ token, model }))

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.type === 'auth_success') { setConnected(true); return }
      if (data.type === 'thinking')     { setThinking(true);  return }
      if (data.type === 'model_switched') {
        setModel(data.model === 'external' ? 'external' : 'local')
        return
      }
      if (['agent_thinking', 'tool_call', 'tool_result'].includes(data.type)) return

      if (data.type === 'push_alert') {
        const alerts = data.alerts as Array<{level: string; message: string; student_name?: string}>
        if (alerts.length > 0) {
          const summary = '🔔 **System Alert**\n' + alerts.map(a =>
            `${a.level === 'high' ? '🔴' : a.level === 'warning' ? '🟡' : 'ℹ️'} ${a.message}`
          ).join('\n')
          setMessages(prev => [...prev, { id: idRef.current++, role: 'system', content: summary }])
          setUnread(n => n + 1)
        }
        return
      }

      if (data.type === 'nav_action') {
        setThinking(false)
        try {
          const payload = JSON.parse(data.message)
          setMessages(prev => [...prev, {
            id: idRef.current++, role: 'assistant',
            content: `Navigating to ${payload.page}...`
          }])
          setTimeout(() => { window.location.href = payload.url }, 800)
        } catch {}
        return
      }

      if (data.type === 'chart_action') {
        setThinking(false)
        try {
          const payload: ChartPayload = JSON.parse(data.message)
          const msg: Message = {
            id: idRef.current++,
            role: 'assistant',
            content: '',          // charts-only bubble (text comes in next message)
            charts: payload.charts,
          }
          setMessages(prev => [...prev, msg])
          if (!openRef.current) setUnread(n => n + 1)
        } catch { /* ignore malformed */ }
        return
      }

      if (data.type === 'message') {
        setThinking(false)
        const msg: Message = { id: idRef.current++, role: 'assistant', content: data.message }
        setMessages(prev => [...prev, msg])
        if (!openRef.current) setUnread(n => n + 1)
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
  }, [])

  useEffect(() => { connect(); return () => ws.current?.close() }, [connect])
  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, thinking, open])
  useEffect(() => { if (open) setUnread(0) }, [open])

  // ── Persistence ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const stored = loadStoredMessages()
    setMessages(stored)
    idRef.current = nextMsgId(stored)
    setStorageReady(true)
  }, [])
  useEffect(() => {
    if (!storageReady) return
    try { window.localStorage.setItem(WIDGET_STORAGE_KEY, JSON.stringify(messages)) } catch {}
  }, [messages, storageReady])

  // ── New conversation ─────────────────────────────────────────────────────────
  function handleNewConversation() {
    const fresh = getInitialMessages()
    setMessages(fresh)
    setThinking(false)
    setInput('')
    idRef.current = nextMsgId(fresh)
    try { window.localStorage.removeItem(WIDGET_STORAGE_KEY) } catch {}
    ws.current?.close()
    ws.current = null
    setConnected(false)
    setTimeout(connect, 100)
  }

  // ── Model switch ─────────────────────────────────────────────────────────────
  function handleModelSwitch(m: 'local' | 'external') {
    if (m === model) return
    setModel(m)
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'switch_model', model: m }))
    }
  }

  // ── Send ─────────────────────────────────────────────────────────────────────
  function handleSend() {
    const msg = input.trim()
    if (!msg || ws.current?.readyState !== WebSocket.OPEN) return
    setMessages(prev => [...prev, { id: idRef.current++, role: 'user', content: msg }])
    ws.current.send(JSON.stringify({ message: msg }))
    setInput('')
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const panelH = expanded ? 'h-[640px]' : 'h-[460px]'
  const panelW = expanded ? 'w-[420px]' : 'w-80'

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">

      {/* ── Chat panel ──────────────────────────────────────────────────────── */}
      {open && (
        <div className={`${panelW} ${panelH} bg-white rounded-2xl shadow-2xl border border-gray-100 flex flex-col overflow-hidden transition-all duration-200`}>

          {/* Header */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-indigo-600 text-white flex-shrink-0">
            <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center">
              <Bot className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-none">AI Assistant</p>
              <p className="text-indigo-200 text-[10px] mt-0.5 flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-indigo-400'}`} />
                {connected ? 'Connected' : 'Connecting…'}
              </p>
            </div>
            <div className="flex items-center gap-1">
              {/* Model toggle */}
              <div className="flex items-center bg-white/10 rounded-lg p-0.5 mr-1">
                <button
                  onClick={() => handleModelSwitch('local')}
                  title="Local model (Qwen3)"
                  className={`px-1.5 py-0.5 rounded text-[9px] font-semibold transition ${
                    model === 'local' ? 'bg-white text-indigo-700' : 'text-indigo-200 hover:text-white'
                  }`}>
                  Local
                </button>
                <button
                  onClick={() => handleModelSwitch('external')}
                  title="MiMo-v2-Omni"
                  className={`px-1.5 py-0.5 rounded text-[9px] font-semibold transition ${
                    model === 'external' ? 'bg-white text-indigo-700' : 'text-indigo-200 hover:text-white'
                  }`}>
                  MiMo
                </button>
              </div>
              <button title="New conversation" onClick={handleNewConversation}
                className="p-1 rounded-lg hover:bg-white/10 transition">
                <PlusCircle className="w-3.5 h-3.5" />
              </button>
              <Link href="/chat" title="Open full chat"
                className="p-1 rounded-lg hover:bg-white/10 transition" onClick={() => setOpen(false)}>
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
              <button title={expanded ? 'Compact' : 'Expand'}
                onClick={() => setExpanded(v => !v)}
                className="p-1 rounded-lg hover:bg-white/10 transition">
                {expanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
              </button>
              <button title="Close" onClick={() => setOpen(false)}
                className="p-1 rounded-lg hover:bg-white/10 transition">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-gray-50/60">
            {messages.map(m => (
              <MessageBubble key={m.id} m={m} isExpanded={expanded} />
            ))}

            {/* Typing indicator */}
            {thinking && (
              <div className="flex gap-2">
                <div className="w-6 h-6 rounded-full bg-white border border-gray-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="w-3 h-3 text-indigo-600" />
                </div>
                <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm px-3 py-2.5">
                  <div className="flex gap-1 items-center">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-gray-100 bg-white flex-shrink-0">
            {!connected && (
              <button onClick={connect}
                className="flex items-center gap-1 text-[10px] text-indigo-500 hover:underline mb-2 mx-auto">
                <RefreshCw className="w-3 h-3" /> Reconnect
              </button>
            )}
            <div className="flex gap-2 items-end bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask anything, or say 'show RPD as pie chart'…"
                rows={1}
                className="flex-1 resize-none text-xs bg-transparent focus:outline-none text-gray-800 placeholder:text-gray-400 max-h-24"
              />
              <button onClick={handleSend}
                disabled={!input.trim() || !connected}
                className="flex-shrink-0 w-7 h-7 flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-200 text-white rounded-lg transition">
                <Send className="w-3 h-3" />
              </button>
            </div>
            <p className="text-center text-[10px] text-gray-300 mt-1.5">Enter to send · Shift+Enter for newline</p>
          </div>
        </div>
      )}

      {/* ── FAB ─────────────────────────────────────────────────────────────── */}
      <button
        onClick={() => setOpen(v => !v)}
        className={`relative w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 ${
          open ? 'bg-gray-700 hover:bg-gray-800' : 'bg-indigo-600 hover:bg-indigo-700'
        }`}
        aria-label="Toggle AI chat"
      >
        <div className={`transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>
          {open
            ? <ChevronDown className="w-6 h-6 text-white" />
            : <Bot className="w-6 h-6 text-white" />
          }
        </div>
        {!open && unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 shadow">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
        {!open && connected && (
          <span className="absolute inset-0 rounded-full bg-indigo-400 opacity-30 animate-ping pointer-events-none" />
        )}
      </button>
    </div>
  )
}
