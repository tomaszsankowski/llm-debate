import { useCallback, useEffect, useState } from 'react'
import {
  ArrowUpRight,
  FlaskConical,
  History as HistoryIcon,
  MessageSquare,
  Plus,
  Radio,
  Settings2,
} from 'lucide-react'
import { api, navigate } from './api/client'
import { Button, Loading, Notice } from './components/ui'
import { ThemeToggle } from './components/ThemeToggle'
import { Conversation } from './pages/Conversation'
import { History } from './pages/History'
import { NewDebate } from './pages/NewDebate'
import type { Config, Health, Settings } from './types'

export default function App() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/new')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState('')
  const [copy, setCopy] = useState<{ config: Config; version: number } | null>(null)
  const refreshHealth = useCallback(() => {
    void api<Health>('/health')
      .then((data) => {
        setHealth(data)
        setError('')
      })
      .catch((error) => setError(error.message))
  }, [])
  useEffect(() => {
    const handler = () => {
      const next = window.location.hash.slice(1) || '/new'
      setRoute(next)
      if (next !== '/new') setCopy(null)
      window.scrollTo(0, 0)
      refreshHealth()
    }
    window.addEventListener('hashchange', handler)
    refreshHealth()
    void api<Settings>('/settings')
      .then(setSettings)
      .catch((error) => setError(error.message))
    const timer = setInterval(refreshHealth, 10000)
    return () => {
      window.removeEventListener('hashchange', handler)
      clearInterval(timer)
    }
  }, [refreshHealth])
  function copyConfig(config: Config) {
    setCopy({ config: structuredClone(config), version: Date.now() })
    navigate('/new')
  }
  const debateId = route.startsWith('/debate/') ? route.split('/')[2] : null
  const title = debateId ? 'Rozmowa' : route === '/history' ? 'Historia debat' : 'Nowa debata'
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#/new">
          <span className="brand-icon">
            <MessageSquare size={21} />
            <span />
          </span>
          <span>
            llm<span className="brand-dot">·</span>debate<small>LABORATORIUM DIALOGU</small>
          </span>
        </a>
        <div className="workspace-label">Środowisko badawcze</div>
        <nav aria-label="Nawigacja główna">
          <a className={!debateId && route !== '/history' ? 'selected' : ''} href="#/new">
            <Plus size={19} /> Nowa debata
          </a>
          <a className={route === '/history' ? 'selected' : ''} href="#/history">
            <HistoryIcon size={19} /> Historia debat
          </a>
          {debateId && (
            <a className="selected" href={`#/debate/${debateId}`}>
              <MessageSquare size={19} /> Rozmowa
            </a>
          )}
        </nav>
        {health?.active_debate_id && (
          <a className="active-debate-link" href={`#/debate/${health.active_debate_id}`}>
            <span className="pulse-dot" />
            <span>
              Trwa debata<small>Przejdź do rozmowy</small>
            </span>
            <ArrowUpRight size={16} />
          </a>
        )}
        <div className="sidebar-bottom">
          <FlaskConical size={22} />
          <p>
            Dwie perspektywy.
            <br />
            Przestrzeń na argumenty.
          </p>
          <div className="model-line">
            Groq <span>·</span> Qwen
          </div>
          <small>
            Dane zapisują się lokalnie.
            <br />
            Generowanie odbywa się przez API.
          </small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <Settings2 size={16} />
            <span>Laboratorium</span>
            <span className="breadcrumb-divider">/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar-actions">
            <div className={`connection ${health?.api_key_configured ? 'ready' : ''}`}>
              <Radio size={14} />
              {error
                ? 'Brak połączenia'
                : health?.api_key_configured
                  ? 'Klucz Groq skonfigurowany'
                  : 'Groq · brak klucza'}
            </div>
            <ThemeToggle />
          </div>
        </header>
        <main>
          {error && (
            <Notice error>
              {error}{' '}
              <Button size="small" variant="ghost" onClick={() => window.location.reload()}>
                Spróbuj ponownie
              </Button>
            </Notice>
          )}
          {!settings || !health ? (
            !error && <Loading />
          ) : debateId ? (
            <Conversation
              key={debateId}
              id={debateId}
              onCopy={copyConfig}
              onChange={refreshHealth}
              settings={settings}
            />
          ) : route === '/history' ? (
            <History />
          ) : (
            <NewDebate
              key={copy?.version || 'new'}
              settings={settings}
              health={health}
              initial={copy?.config}
              onStarted={refreshHealth}
            />
          )}
          <footer className="page-footer">
            <span>llm-debate</span>
            <span>Symulacje konfliktów z wykorzystaniem modeli językowych</span>
          </footer>
        </main>
      </div>
    </div>
  )
}
