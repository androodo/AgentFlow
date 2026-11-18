import { modelAvailable, type Connections, type Mode } from './api'

const names: Record<Mode, string> = {
  demo: 'Demo (no LLM)', ollama: 'Live local Ollama', openai: 'Live OpenAI', anthropic: 'Live Claude',
}

export function ModeOptions({ connections, liveAllowed }: { connections?: Connections; liveAllowed: boolean }) {
  return <>{Object.entries(names).map(([value, label]) => {
    const allowed = value === 'demo' || (liveAllowed && modelAvailable(connections, value as Mode))
    return <option key={value} value={value} disabled={!allowed}>
      {label}{value !== 'demo' && !allowed ? ' · not available' : ''}
    </option>
  })}</>
}
