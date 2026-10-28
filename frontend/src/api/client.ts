export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new Error('Brak połączenia z backendem. Sprawdź, czy aplikacja jest uruchomiona.')
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(
      typeof error.detail === 'string' ? error.detail : `Błąd żądania (${response.status}).`,
    )
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export function navigate(path: string) {
  window.location.hash = path
}
export const date = (value: string) =>
  new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
