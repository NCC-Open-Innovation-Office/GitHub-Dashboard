import { FiAlertTriangle } from 'react-icons/fi'

export default function ErrorBanner({ message }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-red-300">
      <FiAlertTriangle className="shrink-0 text-xl" />
      <span className="text-sm">{message}</span>
    </div>
  )
}
