import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Eye, LoaderCircle, RotateCcw, Sparkles } from 'lucide-react'
import { AgentCard } from '../components/AgentCard'
import { Button, Field, Input, Notice, Select, Textarea } from '../components/ui'
import { api, navigate } from '../api/client'
import { emptyConfig, example } from '../defaults'
import type { Config, Debate, Health, Settings } from '../types'

const DRAFT_KEY = 'llm-debate.draft.v1'
function loadDraft(): Config {
  try {
    const saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null')
    if (saved?.agents?.length === 2 && saved?.agents[0]?.traits)
      return { ...emptyConfig(), ...saved }
  } catch {
    /* Storage may be unavailable. */
  }
  return emptyConfig()
}

export function NewDebate({
  settings,
  health,
  initial,
  onStarted,
}: {
  settings: Settings
  health: Health
  initial?: Config
  onStarted: () => void
}) {
  const [config, setConfig] = useState<Config>(() =>
    initial ? { ...emptyConfig(), ...initial } : loadDraft(),
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<'start' | 'preview' | null>(null)
  const [preview, setPreview] = useState<{ agents: string[]; opening: string } | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const provider = settings.providers.find((item) => item.id === config.provider)!
  const configured = health.providers[config.provider]
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(config))
    } catch {
      /* Draft saving is optional. */
    }
    setPreview(null)
  }, [config])
  function change<K extends keyof Config>(key: K, value: Config[K]) {
    setConfig((old) => ({ ...old, [key]: value }))
  }
  function selectProvider(id: Config['provider']) {
    const next = settings.providers.find((item) => item.id === id)!
    setConfig((old) => ({
      ...old,
      provider: id,
      model: '',
      agents: old.agents.map((agent) => ({
        ...agent,
        max_tokens:
          agent.max_tokens === provider.default_max_tokens
            ? next.default_max_tokens
            : agent.max_tokens,
      })) as Config['agents'],
    }))
  }
  function loadExample(kind: 'migration' | 'pen') {
    const preset = example(kind)
    preset.provider = config.provider
    preset.model = config.model
    for (const agent of preset.agents) agent.max_tokens = provider.default_max_tokens
    setConfig(preset)
  }

  async function submit(form: HTMLFormElement, action: 'start' | 'preview') {
    if (!form.reportValidity()) return
    setBusy(action)
    setError('')
    try {
      if (action === 'preview') {
        setPreview(await api('/prompts/preview', { method: 'POST', body: JSON.stringify(config) }))
        setShowPreview(true)
      } else {
        const debate = await api<Debate>('/debates', {
          method: 'POST',
          body: JSON.stringify(config),
        })
        onStarted()
        navigate(`/debate/${debate.id}`)
      }
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="new-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Przestrzeń eksperymentu</span>
          <h1>
            Nowa debata<span className="accent-dot">.</span>
          </h1>
          <p>Zdefiniuj konflikt. Nadaj stronom głos. Obserwuj, jak zmienia się rozmowa.</p>
        </div>
        <span className="mode-pill">
          <span /> 2 agentów · język polski
        </span>
      </div>
      {!configured && (
        <Notice>
          Dodaj klucz <code>{provider.key_env}</code> do pliku <code>.env</code> i odtwórz kontener
          przez <code>docker compose up -d --force-recreate</code>, aby prowadzić debaty przez{' '}
          {provider.label}. Możesz już przygotować konfigurację i obejrzeć instrukcje.
        </Notice>
      )}
      {health.active_debate_id && (
        <Notice>
          Trwa generowanie w innej debacie.{' '}
          <a href={`#/debate/${health.active_debate_id}`}>Przejdź do rozmowy</a>, aby ją wstrzymać
          lub zatrzymać.
        </Notice>
      )}
      <div className="preset-strip">
        <span>
          <Sparkles size={16} /> Zacznij od przykładu
        </span>
        <Button variant="ghost" size="small" onClick={() => loadExample('migration')}>
          Polityka migracyjna <ArrowRight size={14} />
        </Button>
        <Button variant="ghost" size="small" onClick={() => loadExample('pen')}>
          Spór o długopis <ArrowRight size={14} />
        </Button>
        <Button
          className="reset-button"
          variant="ghost"
          size="small"
          onClick={() => {
            setConfig(emptyConfig())
            setShowPreview(false)
          }}
        >
          <RotateCcw size={14} /> Wyczyść
        </Button>
      </div>
      <form
        id="debate-form"
        onSubmit={(event) => {
          event.preventDefault()
          void submit(event.currentTarget, 'start')
        }}
      >
        <section className="card scenario-card">
          <div className="section-heading">
            <span className="section-number">01</span>
            <div>
              <h2>Wspólny scenariusz</h2>
              <p>Punkt wyjścia, który znają obie strony.</p>
            </div>
          </div>
          <div className="form-grid">
            <Field
              label="Dostawca i model"
              hint="Obaj agenci korzystają z tego modelu przez całą debatę."
              className="full-width"
            >
              <Select
                value={config.provider}
                onChange={(event) => selectProvider(event.target.value as Config['provider'])}
              >
                {settings.providers.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label} · {option.model}
                    {health.providers[option.id] ? '' : ' · brak klucza'}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Nazwa debaty">
              <Input
                required
                maxLength={160}
                value={config.name}
                onChange={(e) => change('name', e.target.value)}
              />
            </Field>
            <Field label="Temat">
              <Input
                required
                maxLength={12000}
                placeholder="Np. polityka migracyjna, konflikt w pracy…"
                value={config.topic}
                onChange={(e) => change('topic', e.target.value)}
              />
            </Field>
            <Field label="Pytanie do rozstrzygnięcia" className="full-width">
              <Input
                required
                maxLength={12000}
                placeholder="O jaką konkretnie kwestię spierają się strony?"
                value={config.question}
                onChange={(e) => change('question', e.target.value)}
              />
            </Field>
            <Field
              label="Wspólny kontekst"
              hint="Fakty i założenia dostępne obu agentom. Pole opcjonalne."
              className="full-width"
            >
              <Textarea
                rows={3}
                maxLength={24000}
                placeholder="Opisz okoliczności konfliktu…"
                value={config.context}
                onChange={(e) => change('context', e.target.value)}
              />
            </Field>
          </div>
          <details className="advanced scenario-advanced">
            <summary>
              Przebieg rozmowy{' '}
              <span>
                {config.rounds} rund · rozpoczyna{' '}
                {config.first_speaker === 'random' ? 'losowanie' : `agent ${config.first_speaker}`}
              </span>
            </summary>
            <div className="advanced-content form-grid">
              <Field label="Cel rozmowy" className="full-width">
                <Input
                  required
                  maxLength={12000}
                  value={config.goal}
                  onChange={(e) => change('goal', e.target.value)}
                />
              </Field>
              <Field label="Rozpoczynający">
                <Select
                  value={config.first_speaker}
                  onChange={(e) =>
                    change('first_speaker', e.target.value as Config['first_speaker'])
                  }
                >
                  <option value="A">Agent A</option>
                  <option value="B">Agent B</option>
                  <option value="random">Losowanie</option>
                </Select>
              </Field>
              <Field label="Limit rund" hint="1 runda = po jednej wypowiedzi obu stron.">
                <Input
                  type="number"
                  required
                  min={1}
                  max={100}
                  value={config.rounds}
                  onChange={(e) => change('rounds', Number(e.target.value))}
                />
              </Field>
              <Field label="Instrukcja otwarcia" className="full-width">
                <Textarea
                  required
                  maxLength={12000}
                  rows={2}
                  value={config.opening}
                  onChange={(e) => change('opening', e.target.value)}
                />
              </Field>
            </div>
          </details>
        </section>
        <div className="section-heading outside-heading">
          <span className="section-number">02</span>
          <div>
            <h2>Dwie perspektywy</h2>
            <p>Każda strona broni swojego stanowiska. Zmiana zdania wynika z argumentów.</p>
          </div>
        </div>
        <div className="agents-grid">
          {config.agents.map((agent, index) => (
            <AgentCard
              key={index}
              agent={agent}
              index={index}
              settings={settings}
              provider={config.provider}
              onChange={(value) =>
                setConfig((old) => {
                  const agents: Config['agents'] = [...old.agents]
                  agents[index] = value
                  return { ...old, agents }
                })
              }
            />
          ))}
        </div>
        {error && <Notice error>{error}</Notice>}
        {showPreview && preview && (
          <section className="card preview-card">
            <div className="section-heading">
              <BookOpen size={22} />
              <div>
                <h2>Instrukcje wysyłane do modelu</h2>
                <p>Wersja {settings.prompt_version}. Każdy agent widzi tylko swój profil.</p>
              </div>
            </div>
            {preview.agents.map((prompt, index) => (
              <details key={index}>
                <summary>
                  Agent {'AB'[index]} — {config.agents[index].name}
                </summary>
                <pre>{prompt}</pre>
              </details>
            ))}
            <p className="subtle">Zadanie pierwszej tury: {preview.opening}</p>
          </section>
        )}
        <div className="start-bar">
          <div>
            <strong>{config.rounds * 2} wypowiedzi</strong>
            <span>
              {provider.label} · {provider.model.split('/').at(-1)} · automatyczny zapis
            </span>
          </div>
          <div className="button-row">
            <Button
              variant="outline"
              disabled={busy !== null}
              onClick={(event) => void submit(event.currentTarget.form!, 'preview')}
            >
              {busy === 'preview' ? <LoaderCircle className="spin" size={16} /> : <Eye size={16} />}{' '}
              Podgląd instrukcji
            </Button>
            <Button
              type="submit"
              disabled={busy !== null || !configured || !!health.active_debate_id}
            >
              {busy === 'start' ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}{' '}
              Rozpocznij debatę
            </Button>
          </div>
        </div>
      </form>
    </div>
  )
}
