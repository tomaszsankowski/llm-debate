import { useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { Button } from './ui'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'llm-debate.theme'

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#212121' : '#ffffff')
}

// Run before rendering React so the first view uses the chosen palette.
export function initializeTheme() {
  let theme: Theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') theme = saved
  } catch {
    /* The toggle also works when browser storage is unavailable. */
  }
  applyTheme(theme)
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const label = theme === 'dark' ? 'Włącz jasny motyw' : 'Włącz ciemny motyw'

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    setTheme(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* Saving is optional. */
    }
  }

  return (
    <Button
      variant="ghost"
      className="theme-toggle"
      aria-label={label}
      title={label}
      onClick={toggle}
    >
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </Button>
  )
}
