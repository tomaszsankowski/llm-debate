import { BrainCircuit, SlidersHorizontal } from 'lucide-react'
import type { Agent, ProviderId, Settings, Traits } from '../types'
import { Checkbox, Field, Input, Slider, Textarea } from './ui'

export function AgentCard({
  agent,
  index,
  settings,
  provider,
  onChange,
}: {
  agent: Agent
  index: number
  settings: Settings
  provider: ProviderId
  onChange: (value: Agent) => void
}) {
  function change<K extends keyof Agent>(key: K, value: Agent[K]) {
    onChange({ ...agent, [key]: value })
  }
  return (
    <section className={`card agent-card agent-${index}`}>
      <div className="agent-heading">
        <span className="avatar">{'AB'[index]}</span>
        <div>
          <span className="eyebrow">Strona {'AB'[index]}</span>
          <h3>Profil uczestnika</h3>
        </div>
        <span className="agent-tag">Niezależny kontekst</span>
      </div>
      <div className="agent-fields">
        <Field label={`Nazwa agenta ${'AB'[index]}`}>
          <Input
            required
            maxLength={160}
            value={agent.name}
            onChange={(e) => change('name', e.target.value)}
          />
        </Field>
        <Field label="Rola">
          <Input
            required
            maxLength={12000}
            placeholder="Kogo reprezentuje ta strona?"
            value={agent.role}
            onChange={(e) => change('role', e.target.value)}
          />
        </Field>
        <Field label="Stanowisko początkowe">
          <Textarea
            required
            maxLength={12000}
            placeholder="Jakiego poglądu broni?"
            value={agent.position}
            onChange={(e) => change('position', e.target.value)}
          />
        </Field>
        <Field label="Cel agenta">
          <Textarea
            required
            maxLength={12000}
            rows={2}
            value={agent.goal}
            onChange={(e) => change('goal', e.target.value)}
          />
        </Field>
      </div>
      <div className="traits-section">
        <h4>
          <SlidersHorizontal size={16} /> Cechy zachowania
        </h4>
        <p className="subtle">Instrukcje kształtujące sposób prowadzenia rozmowy.</p>
        {(
          Object.entries(settings.traits) as [keyof Traits, Settings['traits'][keyof Traits]][]
        ).map(([key, definition]) => (
          <div className="trait" key={key}>
            <div className="trait-label">
              <label id={`${index}-${key}`}>{definition.label}</label>
              <span>
                {agent.traits[key]} <span>/ 5</span>
              </span>
            </div>
            <Slider
              min={1}
              max={5}
              step={1}
              value={[agent.traits[key]]}
              aria-labelledby={`${index}-${key}`}
              aria-label={`${definition.label} — agent ${'AB'[index]}`}
              onValueChange={(values) => change('traits', { ...agent.traits, [key]: values[0] })}
            />
            <div className="trait-ends">
              <span>{definition.low}</span>
              <span>{definition.high}</span>
            </div>
            <p className="trait-description">{definition.instructions[agent.traits[key] - 1]}</p>
          </div>
        ))}
      </div>
      <details className="advanced" open={undefined}>
        <summary>Dodatkowe instrukcje i generowanie</summary>
        <div className="advanced-content">
          <Field label="Dodatkowe instrukcje">
            <Textarea
              maxLength={12000}
              placeholder="Opcjonalne wskazówki dla tej strony…"
              value={agent.instructions}
              onChange={(e) => change('instructions', e.target.value)}
            />
          </Field>
          <Field label="Limit generacji (tokeny)" hint="Limit obejmuje wypowiedź i reasoning.">
            <Input
              type="number"
              min={128}
              max={16384}
              required
              value={agent.max_tokens}
              onChange={(e) => change('max_tokens', Number(e.target.value))}
            />
          </Field>
          <Checkbox
            id={`reasoning-${index}`}
            checked={agent.reasoning}
            onCheckedChange={(value) => change('reasoning', value)}
          >
            <BrainCircuit size={16} /> Włącz reasoning
          </Checkbox>
          <p className="subtle">
            {provider === 'gemini'
              ? 'Zapisuje podsumowania rozumowania i ustawia thinking na niski poziom. Bez zaznaczenia: minimalny thinking, bez podsumowań. Gemini nie gwarantuje całkowitego wyłączenia thinking.'
              : 'Dodatkowy tekst modelu jest zapisywany osobno i nie trafia do rozmówcy.'}
          </p>
        </div>
      </details>
    </section>
  )
}
