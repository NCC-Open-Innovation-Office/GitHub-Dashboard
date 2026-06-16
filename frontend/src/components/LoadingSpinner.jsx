export default function LoadingSpinner({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-slate-400">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-indigo-500" />
      <span className="text-sm">{label}</span>
    </div>
  )
}
