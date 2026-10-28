import type { Debate, Settings, Traits } from '../types'

function Values({ values }: { values: [string, string | number][] }) {
  return (
    <dl className="configuration-values">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value || 'Nie podano'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ConfigDetails({ debate, settings }: { debate: Debate; settings: Settings }) {
  const config = debate.config
  return (
    <details className="card config-details">
      <summary>Konfiguracja debaty</summary>
      <Values
        values={[
          ['Model', debate.model],
          ['Wersja instrukcji', debate.prompt_version],
          [
            'Rozpoczynający',
            `${debate.config.agents[debate.first_agent].name}${config.first_speaker === 'random' ? ' (wylosowano)' : ''}`,
          ],
        ]}
      />
      <details className="config-section">
        <summary>Scenariusz i przebieg</summary>
        <Values
          values={[
            ['Nazwa', config.name],
            ['Temat', config.topic],
            ['Pytanie', config.question],
            ['Kontekst', config.context],
            ['Cel rozmowy', config.goal],
            ['Limit rund', config.rounds],
            ['Instrukcja otwarcia', config.opening],
          ]}
        />
      </details>
      {config.agents.map((agent, index) => (
        <details key={index} className="config-section">
          <summary>
            Agent {'AB'[index]} — {agent.name}
          </summary>
          <Values
            values={[
              ['Rola', agent.role],
              ['Stanowisko początkowe', agent.position],
              ['Cel', agent.goal],
              ['Dodatkowe instrukcje', agent.instructions],
              ['Limit generacji', `${agent.max_tokens} tokenów`],
              ['Reasoning', agent.reasoning ? 'Włączone' : 'Wyłączone'],
              ...(Object.entries(agent.traits) as [keyof Traits, number][]).map(
                ([key, value]): [string, string] => [
                  settings.traits[key].label,
                  `${value}/5 — ${settings.traits[key].instructions[value - 1]}`,
                ],
              ),
            ]}
          />
        </details>
      ))}
    </details>
  )
}
