'use client'
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const COLORS = { High: '#dc2626', Medium: '#d97706', Low: '#16a34a' }

interface Props {
  distribution: Record<string, number>
}

export default function RiskChart({ distribution }: Props) {
  const data = Object.entries(distribution).map(([name, value]) => ({ name, value }))
  if (data.length === 0) return <p className="text-sm text-gray-400 text-center py-8">No data</p>

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={90}
          paddingAngle={3}
          dataKey="value"
        >
          {data.map((entry) => (
            <Cell
              key={entry.name}
              fill={COLORS[entry.name as keyof typeof COLORS] ?? '#6b7280'}
            />
          ))}
        </Pie>
        <Tooltip formatter={(v: number) => [`${v} students`, '']} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
