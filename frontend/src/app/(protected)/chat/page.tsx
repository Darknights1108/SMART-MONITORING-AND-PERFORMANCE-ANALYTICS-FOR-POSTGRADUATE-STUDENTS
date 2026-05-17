'use client'
import { useEffect, useRef, useState } from 'react'
import { Send, Bot, User, RefreshCw, ChevronDown } from 'lucide-react'
import { getToken } from '@/lib/auth'
import { wsUrl } from '@/lib/api'

type Role = 'user' | 'assistant' | 'system'
interface Message { id: number; role: Role; content: string; timestamp?: string }
interface Step { type: string; content: string }

export default function ChatPage() {
  const [messages, setMessages]   = useState<Message[]>([
    { id: 0, role: 'assistant', content: 'Hello! I\'m your AI Assistant. Ask me anything about students, milestones, risk predictions, or deadlines.' },
  ])
  const [steps, setSteps]     = useState<Step[]>([])
  const [input, setInput]     = useState('')
  const [thinking, setThinking] = useState(false)
  const [showSteps, setShowSteps] = useState(false)
  const [connected, setConnected] = useState(false)
  const ws  = useRef<WebSocket | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const idRef = useRef(1)

  function scrollBottom() {
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => { scrollBottom() }, [messages, thinking])

  useEffect(() => {
    connect()
    return () => ws.current?.close()
  }, [])

  function connect() {
    const token = getToken()
    if (!token) return

    const socket = new WebSocket(wsUrl())
    ws.current = socket

    socket.onopen = () => {
      socket.send(JSON.stringify({ token }))
    }

    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.type === 'auth_success') {
        setConnected(true)
        return
      }
      if (data.type === 'thinking') {
        setThinking(true)
        setSteps([])
        return
      }
      if (data.type === 'agent_thinking' || data.type === 'tool_call' || data.type === 'tool_result') {
        setSteps(prev => [...prev, { type: data.type, content: data.content || data.tool || '' }])
        return
      }
      if (data.type === 'message' || data.type === 'chart') {
        setThinking(false)
        const msg: Message = {
          id: idRef.current++,
          role: 'assistant',
          content: data.message,
          timestamp: data.timestamp,
        }
        setMessages(prev => [...prev, msg])
        return
      }
      if (data.type === 'error') {
        setThinking(false)
        setMessages(prev => [...prev, {
          id: idRef.current++,
          role: 'system',
          content: `⚠️ ${data.message}`,
        }])
      }
    }

    socket.onclose = () => { setConnected(false) }
    socket.onerror = () => { setConnected(false) }
  }

  function handleSend() {
    const msg = input.trim()
    if (!msg || !ws.current || ws.current.readyState !== WebSocket.OPEN) return

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
        {steps.length > 0 && (
          <button
            onClick={() => setShowSteps(!showSteps)}
            className="flex items-center gap-1 text-xs text-indigo-600 border border-indigo-200 rounded-lg px-3 py-1.5 hover:bg-indigo-50"
          >
            Agent steps ({steps.length})
            <ChevronDown className={`w-3 h-3 transition-transform ${showSteps ? 'rotate-180' : ''}`} />
          </button>
        )}
      </div>

      {/* Agent steps panel */}
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
        {messages.map(m => (
          <div key={m.id} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
              m.role === 'user'      ? 'bg-indigo-600' :
              m.role === 'system'   ? 'bg-red-100' :
                                      'bg-gray-100'
            }`}>
              {m.role === 'user'
                ? <User className="w-4 h-4 text-white" />
                : <Bot className={`w-4 h-4 ${m.role === 'system' ? 'text-red-500' : 'text-gray-600'}`} />
              }
            </div>
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-indigo-600 text-white rounded-tr-sm'
                : m.role === 'system'
                ? 'bg-red-50 text-red-800 border border-red-100'
                : 'bg-white border border-gray-100 shadow-sm text-gray-800 rounded-tl-sm'
            }`}>
              {m.content}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-gray-600" />
            </div>
            <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
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
            <button
              onClick={connect}
              className="flex items-center gap-2 mx-auto text-sm text-indigo-600 hover:underline"
            >
              <RefreshCw className="w-4 h-4" /> Reconnect
            </button>
          </div>
        )}
        <div className="flex gap-3 bg-white border border-gray-200 rounded-2xl p-2 shadow-sm">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about students, risks, deadlines, or send emails…"
            rows={1}
            className="flex-1 resize-none px-3 py-2 text-sm focus:outline-none bg-transparent"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !connected}
            className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-200 text-white rounded-xl transition"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-center text-xs text-gray-400 mt-2">Press Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}
