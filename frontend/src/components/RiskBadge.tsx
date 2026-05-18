type Label = 'High' | 'Medium' | 'Low' | null | undefined

const styles: Record<string, string> = {
  High:   'bg-red-100 text-red-700 border-red-200',
  Medium: 'bg-amber-100 text-amber-700 border-amber-200',
  Low:    'bg-green-100 text-green-700 border-green-200',
}

const dots: Record<string, string> = {
  High:   'bg-red-500',
  Medium: 'bg-amber-500',
  Low:    'bg-green-500',
}

export default function RiskBadge({ label }: { label: Label; score?: number | null }) {
  if (!label) return <span className="text-xs text-gray-400">â€”</span>
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${styles[label]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[label]}`} />
      {label}
    </span>
  )
}

