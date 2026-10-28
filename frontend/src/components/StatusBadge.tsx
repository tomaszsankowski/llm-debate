import type { Outcome, Status } from '../types'

export const statusLabels: Record<Status, string> = {
  running: 'W toku',
  pausing: 'Wstrzymywanie',
  waiting: 'Limit API · oczekiwanie',
  paused: 'W pauzie',
  error: 'Błąd',
  stopped: 'Zatrzymana',
  completed: 'Zakończona',
  interrupted: 'Przerwana',
}
export const outcomeLabels: Record<Outcome, string> = {
  unrated: 'Nieocenione',
  consensus: 'Konsensus',
  partial: 'Częściowa zgodność',
  disagreement: 'Brak konsensusu',
}
export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span />
      {statusLabels[status]}
    </span>
  )
}
