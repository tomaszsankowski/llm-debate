import { useState } from 'react'
import { api } from '../api/client'
import type { Attempt } from '../types'
import { Button, Notice } from './ui'

export function AttemptDetails({ attempt, debateId }: { attempt: Attempt; debateId: string }) {
  const [request, setRequest] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  async function loadRequest() {
    setLoading(true)
    setError('')
    try {
      const full = await api<Attempt>(`/debates/${debateId}/attempts/${attempt.id}`)
      setRequest(full.request || {})
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setLoading(false)
    }
  }
  return (
    <details className="message-details">
      <summary>
        Szczegóły generowania{' '}
        {attempt.duration_ms !== null && <span>· {(attempt.duration_ms / 1000).toFixed(1)} s</span>}
      </summary>
      <div>
        {attempt.reasoning && (
          <details className="reasoning-details">
            <summary>Reasoning — dodatkowy tekst modelu</summary>
            <p className="subtle">
              Materiał do analizy, nie gwarantowany zapis przyczyn zachowania. Niewidoczny dla
              rozmówcy.
            </p>
            <pre>{attempt.reasoning}</pre>
          </details>
        )}
        <dl className="metadata">
          <dt>Próba</dt>
          <dd>{attempt.number}</dd>
          <dt>Zakończenie</dt>
          <dd>{attempt.finish_reason || 'brak'}</dd>
          <dt>Tokeny wejścia / wyjścia</dt>
          <dd>
            {String(attempt.usage?.prompt_tokens ?? '—')} /{' '}
            {String(attempt.usage?.completion_tokens ?? '—')}
          </dd>
        </dl>
        <details>
          <summary>Metadane odpowiedzi</summary>
          <pre>{JSON.stringify({ ...attempt.metadata, usage: attempt.usage }, null, 2)}</pre>
        </details>
        <Button
          variant="ghost"
          size="small"
          onClick={() => (request ? setRequest(null) : void loadRequest())}
          disabled={loading}
        >
          {loading ? 'Wczytywanie…' : request ? 'Ukryj wysłane żądanie' : 'Pokaż wysłane żądanie'}
        </Button>
        {error && <Notice error>{error}</Notice>}
        {request && <pre className="request-json">{JSON.stringify(request, null, 2)}</pre>}
      </div>
    </details>
  )
}
