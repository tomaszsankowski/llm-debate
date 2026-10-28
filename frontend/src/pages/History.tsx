import { useEffect, useState } from 'react'
import { ArrowRight, Download, History as HistoryIcon, Plus, Search, Trash2 } from 'lucide-react'
import { api, date } from '../api/client'
import { outcomeLabels, StatusBadge } from '../components/StatusBadge'
import { Button, Input, Loading, Notice } from '../components/ui'
import type { Summary } from '../types'

export function History() {
  const [items, setItems] = useState<Summary[] | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)
  async function deleteDebate(item: Summary) {
    if (
      !window.confirm(
        `Usunąć debatę „${item.name}”? Rozmowa, próby generowania i notatki zostaną trwale usunięte.`,
      )
    )
      return
    setDeleting(item.id)
    setError('')
    try {
      await api<void>(`/debates/${item.id}`, { method: 'DELETE' })
      setItems((current) => current?.filter((entry) => entry.id !== item.id) ?? null)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Nie udało się usunąć debaty.')
    } finally {
      setDeleting(null)
    }
  }
  useEffect(() => {
    let alive = true
    const load = () =>
      api<Summary[]>('/debates')
        .then((data) => {
          if (alive) {
            setItems(data)
            setError('')
          }
        })
        .catch((error) => {
          if (alive) setError(error.message)
        })
    void load()
    const timer = setInterval(() => void load(), 5000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
  const filtered = (items || []).filter((item) =>
    item.name.toLocaleLowerCase('pl').includes(query.toLocaleLowerCase('pl')),
  )
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Archiwum eksperymentów</span>
          <h1>
            Historia debat<span className="accent-dot">.</span>
          </h1>
          <p>Wróć do rozmów, porównaj stanowiska i zachowaj materiał do analizy.</p>
        </div>
        <Button asChild>
          <a href="#/new">
            <Plus size={17} /> Nowa debata
          </a>
        </Button>
      </div>
      {error && <Notice error>{error}</Notice>}
      <div className="history-stats">
        <div>
          <span>Wszystkie debaty</span>
          <strong>{items?.length ?? '—'}</strong>
        </div>
        <div>
          <span>Zakończone</span>
          <strong>{items?.filter((item) => item.status === 'completed').length ?? '—'}</strong>
        </div>
        <div>
          <span>Zapisane wypowiedzi</span>
          <strong>{items?.reduce((sum, item) => sum + item.turns, 0) ?? '—'}</strong>
        </div>
      </div>
      <section className="card history-card">
        <div className="history-toolbar">
          <h2>
            Zapisane rozmowy <span className="count">{filtered.length}</span>
          </h2>
          <div className="search-field">
            <Search size={17} />
            <Input
              aria-label="Wyszukaj debatę"
              placeholder="Szukaj po nazwie…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>
        {!items && !error ? (
          <Loading />
        ) : !filtered.length ? (
          <div className="empty-state">
            <span>
              <HistoryIcon size={29} />
            </span>
            <h3>{query ? 'Brak pasujących debat' : 'Tu zacznie się Twoje archiwum'}</h3>
            <p>
              {query
                ? 'Spróbuj użyć innego fragmentu nazwy.'
                : 'Rozpocznij rozmowę dwóch agentów. Jej zapis pojawi się tutaj automatycznie.'}
            </p>
            {!query && (
              <Button asChild variant="outline">
                <a href="#/new">
                  Przygotuj pierwszą debatę <ArrowRight size={16} />
                </a>
              </Button>
            )}
          </div>
        ) : (
          <div className="table-scroll">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Debata</th>
                  <th>Status</th>
                  <th>Przebieg</th>
                  <th>Ocena badacza</th>
                  <th>
                    <span className="sr-only">Akcje</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <a className="debate-link" href={`#/debate/${item.id}`}>
                        {item.name}
                      </a>
                      <span className="history-date">{date(item.created_at)}</span>
                    </td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>
                      {item.turns} / {item.rounds * 2}
                      <span className="history-date">wypowiedzi</span>
                    </td>
                    <td>
                      <span className="outcome-label">{outcomeLabels[item.outcome]}</span>
                    </td>
                    <td>
                      <div className="button-row">
                        <a
                          className="icon-button"
                          title="Pobierz JSON"
                          aria-label={`Eksport JSON: ${item.name}`}
                          href={`/api/debates/${item.id}/export`}
                          download
                        >
                          <Download size={17} />
                        </a>
                        <button
                          type="button"
                          className="icon-button"
                          title={
                            ['running', 'pausing', 'waiting'].includes(item.status)
                              ? 'Najpierw wstrzymaj lub zatrzymaj debatę'
                              : 'Usuń debatę'
                          }
                          aria-label={`Usuń: ${item.name}`}
                          disabled={
                            deleting !== null ||
                            ['running', 'pausing', 'waiting'].includes(item.status)
                          }
                          onClick={() => void deleteDebate(item)}
                        >
                          <Trash2 size={17} />
                        </button>
                        <a
                          className="icon-button"
                          title="Otwórz debatę"
                          aria-label={`Otwórz: ${item.name}`}
                          href={`#/debate/${item.id}`}
                        >
                          <ArrowRight size={17} />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
