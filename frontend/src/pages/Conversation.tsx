import { useEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowLeft,
  Copy,
  Download,
  MessageSquare,
  Pause,
  Play,
  Save,
  SkipForward,
  Square,
} from 'lucide-react'
import { api, date } from '../api/client'
import { AttemptDetails } from '../components/AttemptDetails'
import { ConfigDetails } from '../components/ConfigDetails'
import { outcomeLabels, StatusBadge } from '../components/StatusBadge'
import { Button, Field, Loading, Notice, Select, Textarea } from '../components/ui'
import type { Annotations, Config, Debate, Outcome, Settings } from '../types'

export function Conversation({
  id,
  onCopy,
  onChange,
  settings,
}: {
  id: string
  onCopy: (config: Config) => void
  onChange: () => void
  settings: Settings
}) {
  const [debate, setDebate] = useState<Debate | null>(null)
  const [error, setError] = useState('')
  const [disconnected, setDisconnected] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    const accept = (next: Debate) => {
      if (alive) setDebate((old) => (!old || next.revision >= old.revision ? next : old))
    }
    void api<Debate>(`/debates/${id}`)
      .then(accept)
      .catch((error) => {
        if (alive) setError(error.message)
      })
    const source = new EventSource(`/api/debates/${id}/events`)
    source.addEventListener('snapshot', (event) => {
      accept(JSON.parse((event as MessageEvent).data))
      setDisconnected(false)
    })
    source.onerror = () => {
      if (alive) setDisconnected(true)
    }
    return () => {
      alive = false
      source.close()
    }
  }, [id])
  async function control(action: 'pause' | 'resume' | 'step' | 'stop') {
    setBusy(true)
    setError('')
    try {
      const next = await api<Debate>(`/debates/${id}/control`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      setDebate((old) => (!old || next.revision >= old.revision ? next : old))
      onChange()
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(false)
    }
  }
  if (!debate) return error ? <Notice error>{error}</Notice> : <Loading />
  return (
    <ConversationContent
      debate={debate}
      busy={busy}
      error={error}
      disconnected={disconnected}
      control={control}
      onCopy={onCopy}
      settings={settings}
    />
  )
}

function ConversationContent({
  debate,
  busy,
  error,
  disconnected,
  control,
  onCopy,
  settings,
}: {
  debate: Debate
  busy: boolean
  error: string
  disconnected: boolean
  control: (action: 'pause' | 'resume' | 'step' | 'stop') => Promise<void>
  onCopy: (config: Config) => void
  settings: Settings
}) {
  const [follow, setFollow] = useState(true)
  const viewport = useRef<HTMLDivElement>(null)
  const current = debate.attempts.find((attempt) => attempt.status === 'streaming')
  const failed = debate.attempts.filter((attempt) =>
    ['failed', 'interrupted'].includes(attempt.status),
  )
  const active = ['running', 'pausing', 'waiting'].includes(debate.status)
  const terminal = ['stopped', 'completed'].includes(debate.status)
  const nextIndex = (debate.first_agent + debate.messages.length) % 2
  useEffect(() => {
    if (follow && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight
  }, [follow, debate.messages.length, current?.content, current?.reasoning])
  return (
    <>
      <a className="back-link" href="#/history">
        <ArrowLeft size={14} /> Wszystkie debaty
      </a>
      <div className="page-heading conversation-heading">
        <div>
          <span className="eyebrow">Zapis eksperymentu</span>
          <h1>{debate.config.name}</h1>
          <p>{debate.config.question}</p>
        </div>
        <div className="button-row">
          <Button variant="outline" onClick={() => onCopy(debate.config)}>
            <Copy size={16} /> Użyj tych ustawień
          </Button>
          <Button variant="outline" asChild>
            <a href={`/api/debates/${debate.id}/export`} download>
              <Download size={16} /> Eksport JSON
            </a>
          </Button>
        </div>
      </div>
      {error && <Notice error>{error}</Notice>}
      {disconnected && (
        <Notice>
          Połączenie z podglądem zostało przerwane. Trwa ponowne łączenie; zapisane wypowiedzi
          pozostają dostępne.
        </Notice>
      )}
      <div className="conversation-layout">
        <section className="card transcript-card">
          <div className="transcript-header">
            <div>
              <StatusBadge status={debate.status} />
              <span className="subtle">
                {debate.messages.length} / {debate.config.rounds * 2} wypowiedzi
              </span>
            </div>
            <span className="subtle">
              Runda {Math.min(debate.config.rounds, Math.floor(debate.messages.length / 2) + 1)} z{' '}
              {debate.config.rounds}
            </span>
          </div>
          <div className="progress-track">
            <div
              style={{ width: `${(100 * debate.messages.length) / (debate.config.rounds * 2)}%` }}
            />
          </div>
          <div className="transcript" ref={viewport} aria-label="Przebieg debaty" tabIndex={0}>
            <div className="conversation-start">
              <span>
                <MessageSquare size={15} />
              </span>
              <strong>Początek rozmowy</strong>
              <p>
                {date(debate.created_at)} · rozpoczyna{' '}
                {debate.config.agents[debate.first_agent].name}
              </p>
            </div>
            {debate.messages.map((message) => {
              const attempt = debate.attempts.find((item) => item.id === message.attempt_id)
              return (
                <article
                  className={`message agent-${message.agent_index}`}
                  key={message.id}
                  data-testid="public-message"
                >
                  <div className="message-author">
                    <span className="avatar">{'AB'[message.agent_index]}</span>
                    <strong>{debate.config.agents[message.agent_index].name}</strong>
                    <span>
                      Runda {message.round} · tura {message.turn}
                    </span>
                  </div>
                  <div className="message-bubble">
                    <p>{message.content}</p>
                    {attempt && <AttemptDetails attempt={attempt} debateId={debate.id} />}
                  </div>
                </article>
              )
            })}
            {current && (
              <article className={`message agent-${current.agent_index} draft-message`}>
                <div className="message-author">
                  <span className="avatar">{'AB'[current.agent_index]}</span>
                  <strong>{debate.config.agents[current.agent_index].name}</strong>
                  <span className="typing-label">
                    Tworzy wypowiedź<span className="typing-dots">…</span>
                  </span>
                </div>
                <div className="message-bubble">
                  <p>
                    {current.content ||
                      (current.reasoning
                        ? 'Model generuje reasoning. Oczekiwanie na publiczną wypowiedź…'
                        : 'Oczekiwanie na odpowiedź modelu…')}
                  </p>
                  <span className="draft-label">W trakcie generowania · zapis roboczy</span>
                </div>
              </article>
            )}
            {!current && !terminal && (
              <div className="next-speaker">
                Następna wypowiedź: <strong>{debate.config.agents[nextIndex].name}</strong>
              </div>
            )}
            {terminal && (
              <div className="conversation-end">
                <span />
                <strong>
                  {debate.status === 'completed' ? 'Debata zakończona' : 'Debata zatrzymana'}
                </strong>
                <span />
              </div>
            )}
          </div>
          <div className="conversation-status" role="status">
            {debate.reason ||
              (debate.status === 'running'
                ? 'Agenci rozmawiają. Każda ukończona wypowiedź zapisuje się automatycznie.'
                : debate.status === 'pausing'
                  ? 'Bieżąca wypowiedź zostanie ukończona, a następna wstrzymana.'
                  : 'Debata jest w pauzie. Można wygenerować jedną wypowiedź lub wznowić rozmowę.')}
            {debate.retry_at && <span> Ponowienie: {date(debate.retry_at)}.</span>}
          </div>
          <div className="conversation-controls">
            <div className="button-row">
              {active ? (
                <Button
                  variant="outline"
                  disabled={busy || debate.status === 'pausing'}
                  onClick={() => void control('pause')}
                >
                  <Pause size={15} /> Pauza
                </Button>
              ) : (
                <Button disabled={busy || terminal} onClick={() => void control('resume')}>
                  <Play size={15} /> Wznów
                </Button>
              )}
              <Button
                variant="outline"
                disabled={busy || active || terminal}
                onClick={() => void control('step')}
              >
                <SkipForward size={16} /> Jedna wypowiedź
              </Button>
              <Button
                variant="ghost"
                disabled={busy || terminal}
                onClick={() => void control('stop')}
              >
                <Square size={14} /> Zatrzymaj
              </Button>
            </div>
            <Button
              variant="ghost"
              size="small"
              aria-pressed={follow}
              onClick={() => setFollow((value) => !value)}
            >
              <ArrowDown size={15} />
              {follow ? 'Śledzenie włączone' : 'Śledź rozmowę'}
            </Button>
          </div>
        </section>
        <aside className="conversation-sidebar">
          <section className="card participant-card">
            <h3>Uczestnicy</h3>
            {debate.config.agents.map((agent, index) => (
              <div key={index} className={`participant agent-${index}`}>
                <span className="avatar">{'AB'[index]}</span>
                <div>
                  <strong>{agent.name}</strong>
                  <p>{agent.position}</p>
                </div>
              </div>
            ))}
          </section>
          <AnnotationsForm debateId={debate.id} initial={debate.annotations} />
          <ConfigDetails debate={debate} settings={settings} />
        </aside>
      </div>
      {failed.length > 0 && (
        <section className="card attempts-card">
          <h2>
            Nieukończone próby <span className="count">{failed.length}</span>
          </h2>
          <p className="subtle">
            Nie są częścią publicznej rozmowy i nie trafiają do drugiego agenta. Pozostają w
            eksporcie.
          </p>
          {failed.map((attempt) => (
            <details key={attempt.id} className="failed-attempt">
              <summary>
                Tura {attempt.turn} · próba {attempt.number} · agent {'AB'[attempt.agent_index]}
                <span>{attempt.error?.message}</span>
              </summary>
              {attempt.content && <pre>{attempt.content}</pre>}
              <AttemptDetails attempt={attempt} debateId={debate.id} />
            </details>
          ))}
        </section>
      )}
    </>
  )
}

function AnnotationsForm({ debateId, initial }: { debateId: string; initial: Annotations }) {
  const [annotations, setAnnotations] = useState(initial)
  const [state, setState] = useState('')
  const [error, setError] = useState('')
  async function save() {
    setState('Zapisywanie…')
    setError('')
    try {
      await api(`/debates/${debateId}/annotations`, {
        method: 'PATCH',
        body: JSON.stringify(annotations),
      })
      setState('Zapisano')
    } catch (error) {
      setError((error as Error).message)
      setState('')
    }
  }
  return (
    <section className="card notes-card">
      <h3>Notatnik badacza</h3>
      <p className="subtle">Notatki i ocena są widoczne tylko tutaj.</p>
      <Field label="Wynik debaty">
        <Select
          value={annotations.outcome}
          onChange={(event) => {
            setAnnotations({ ...annotations, outcome: event.target.value as Outcome })
            setState('Niezapisane zmiany')
          }}
        >
          {Object.entries(outcomeLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Notatki">
        <Textarea
          rows={5}
          maxLength={20000}
          value={annotations.notes}
          placeholder="Strategie, ważne argumenty, zmiany stanowisk…"
          onChange={(event) => {
            setAnnotations({ ...annotations, notes: event.target.value })
            setState('Niezapisane zmiany')
          }}
        />
      </Field>
      <div className="notes-footer">
        <Button
          variant="outline"
          size="small"
          disabled={state === 'Zapisywanie…'}
          onClick={() => void save()}
        >
          <Save size={14} /> Zapisz notatki
        </Button>
        <span className="subtle" role="status">
          {state}
        </span>
      </div>
      {error && <Notice error>{error}</Notice>}
    </section>
  )
}
