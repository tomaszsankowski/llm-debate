import type { Agent, Config } from './types'

function agent(name: string): Agent {
  return {
    name,
    role: '',
    position: '',
    goal: 'Przekonać rozmówcę do swojego stanowiska.',
    instructions: '',
    traits: { escalation: 3, openness: 3, reactivity: 3, risk: 3, aggression: 3, dominance: 3 },
    max_tokens: 2048,
    reasoning: false,
  }
}
export function emptyConfig(): Config {
  return {
    name: 'Nowa debata',
    topic: '',
    question: '',
    context: '',
    goal: 'Wymiana argumentów i próba przekonania rozmówcy',
    first_speaker: 'A',
    rounds: 10,
    opening: 'Przedstaw swoje stanowisko i najważniejsze argumenty na jego poparcie.',
    agents: [agent('Agent A'), agent('Agent B')],
  }
}
export function example(kind: 'migration' | 'pen'): Config {
  const config = emptyConfig()
  if (kind === 'migration') {
    config.name = 'Polityka migracyjna'
    config.topic = 'Imigracja i polityka państwa'
    config.question = 'Czy państwo powinno ułatwiać imigrację?'
    config.context =
      'Debata dotyczy fikcyjnego państwa demokratycznego. Rozmawiajcie o zasadach polityki migracyjnej i ich skutkach; nie zakładajcie niepodanych danych statystycznych.'
    Object.assign(config.agents[0], {
      name: 'Zwolennik otwarcia',
      role: 'Osoba opowiadająca się za otwartą polityką migracyjną',
      position: 'Państwo powinno ułatwiać imigrację i wspierać integrację przyjeżdżających osób.',
    })
    Object.assign(config.agents[1], {
      name: 'Zwolennik ograniczeń',
      role: 'Osoba opowiadająca się za ograniczeniem imigracji',
      position:
        'Państwo powinno ograniczać imigrację i ostrożnie oceniać jej koszty społeczne oraz organizacyjne.',
    })
  } else {
    config.name = 'Spór o pożyczony długopis'
    config.topic = 'Korzystanie z cudzych rzeczy'
    config.question = 'Czy można pożyczyć rzecz współpracownika bez pytania?'
    config.context =
      'Bartek wziął długopis Anny z jej biurka bez pytania i oddał go po spotkaniu. Anna w tym czasie potrzebowała długopisu. Wcześniej nie ustalili zasad pożyczania.'
    Object.assign(config.agents[0], {
      name: 'Anna',
      role: 'Właścicielka pożyczonego długopisu',
      position: 'Trzeba pytać przed pożyczeniem mojej rzeczy, nawet na chwilę.',
      goal: 'Przekonać Bartka, by pytał przed pożyczeniem rzeczy.',
    })
    Object.assign(config.agents[1], {
      name: 'Bartek',
      role: 'Współpracownik, który pożyczył długopis',
      position: 'Chwilowe pożyczenie zwykłego długopisu w pracy nie wymaga pytania.',
      goal: 'Przekonać Annę, że krótkie pożyczenie zwykłych rzeczy jest dopuszczalne.',
    })
  }
  return config
}
