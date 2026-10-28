export type Traits = Record<
  'escalation' | 'openness' | 'reactivity' | 'risk' | 'aggression' | 'dominance',
  number
>
export type Agent = {
  name: string
  role: string
  position: string
  goal: string
  instructions: string
  traits: Traits
  max_tokens: number
  reasoning: boolean
}
export type ProviderId = 'groq' | 'gemini'
export type ProviderOption = {
  id: ProviderId
  label: string
  model: string
  key_env: string
  default_max_tokens: number
}
export type Config = {
  provider: ProviderId
  model?: string
  name: string
  topic: string
  question: string
  context: string
  goal: string
  first_speaker: 'A' | 'B' | 'random'
  rounds: number
  opening: string
  agents: [Agent, Agent]
}
export type Settings = {
  providers: ProviderOption[]
  prompt_version: string
  levels: string[]
  traits: Record<keyof Traits, { label: string; low: string; high: string; instructions: string[] }>
}
export type Health = {
  api_key_configured: boolean
  providers: Record<ProviderId, boolean>
  active_debate_id: string | null
}
export type Status =
  | 'running'
  | 'pausing'
  | 'waiting'
  | 'paused'
  | 'error'
  | 'stopped'
  | 'completed'
  | 'interrupted'
export type Outcome = 'unrated' | 'consensus' | 'partial' | 'disagreement'
export type Annotations = { notes: string; outcome: Outcome }
export type Attempt = {
  id: string
  agent_index: number
  turn: number
  round: number
  number: number
  status: 'streaming' | 'completed' | 'failed' | 'interrupted'
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  content: string
  reasoning: string
  finish_reason: string | null
  usage: Record<string, unknown> | null
  metadata: Record<string, unknown>
  error: { code: string; message: string; retry_after?: number | null } | null
  request?: Record<string, unknown>
}
export type Message = {
  id: string
  attempt_id: string
  agent_index: number
  turn: number
  round: number
  content: string
  created_at: string
}
export type Debate = {
  id: string
  schema_version: number
  prompt_version: string
  revision: number
  created_at: string
  updated_at: string
  model: string
  provider: string
  config: Config
  first_agent: number
  status: Status
  reason: string | null
  retry_at: string | null
  messages: Message[]
  attempts: Attempt[]
  annotations: Annotations
}
export type Summary = {
  id: string
  name: string
  topic: string
  created_at: string
  status: Status
  outcome: Outcome
  turns: number
  rounds: number
}
