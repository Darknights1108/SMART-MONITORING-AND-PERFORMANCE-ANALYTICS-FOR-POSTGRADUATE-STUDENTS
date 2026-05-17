import { type LucideIcon } from 'lucide-react'

interface Props {
  title: string
  value: number | string
  sub?: string
  icon: LucideIcon
  color?: 'indigo' | 'red' | 'amber' | 'green' | 'blue'
}

const palette = {
  indigo: { bg: 'bg-indigo-50', icon: 'text-indigo-600', val: 'text-indigo-700' },
  red:    { bg: 'bg-red-50',    icon: 'text-red-600',    val: 'text-red-700'    },
  amber:  { bg: 'bg-amber-50',  icon: 'text-amber-600',  val: 'text-amber-700'  },
  green:  { bg: 'bg-green-50',  icon: 'text-green-600',  val: 'text-green-700'  },
  blue:   { bg: 'bg-blue-50',   icon: 'text-blue-600',   val: 'text-blue-700'   },
}

export default function StatsCard({ title, value, sub, icon: Icon, color = 'indigo' }: Props) {
  const c = palette[color]
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className={`text-3xl font-bold mt-1 ${c.val}`}>{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
        </div>
        <div className={`${c.bg} p-3 rounded-xl`}>
          <Icon className={`w-5 h-5 ${c.icon}`} />
        </div>
      </div>
    </div>
  )
}
