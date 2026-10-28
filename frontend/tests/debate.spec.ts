import { expect, test } from '@playwright/test'

test('konfiguracja, SSE, pauza, krok, zapis, eksport i ponowne użycie ustawień', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await page.getByRole('button', { name: 'Spór o długopis' }).click()
  await page.locator('summary').filter({ hasText: 'Przebieg rozmowy' }).click()
  await page.getByLabel('Limit rund', { exact: true }).fill('2')
  const agentA = page.locator('.agent-card').first()
  await agentA.locator('summary').click()
  await agentA.getByRole('checkbox', { name: 'Włącz reasoning' }).check()
  await page.getByRole('button', { name: 'Podgląd instrukcji' }).click()
  await page.locator('.preview-card details').first().locator('summary').click()
  await expect(page.locator('.preview-card pre').first()).toContainText('Nazwa: Anna')
  await expect(page.locator('.preview-card pre').first()).not.toContainText('Nazwa: Bartek')
  await page.screenshot({ path: testInfo.outputPath('configuration.png'), fullPage: true })
  await page.getByRole('button', { name: 'Rozpocznij debatę' }).click()
  await expect(page).toHaveURL(/#\/debate\//)
  await expect(page.locator('.draft-message')).toBeVisible()
  await page.getByRole('button', { name: 'Pauza', exact: true }).click()
  await expect(page.locator('.status-badge')).toHaveText('W pauzie')
  await expect(page.getByTestId('public-message')).toHaveCount(1)
  await page.reload()
  await expect(page.getByTestId('public-message')).toHaveCount(1)
  await page.getByRole('button', { name: 'Jedna wypowiedź' }).click()
  await expect(page.locator('.status-badge')).toHaveText('W pauzie')
  await expect(page.getByTestId('public-message')).toHaveCount(2)
  await page.getByRole('button', { name: 'Wznów', exact: true }).click()
  await expect(page.locator('.status-badge')).toHaveText('Zakończona', { timeout: 20000 })
  await expect(page.getByTestId('public-message')).toHaveCount(4)
  await page
    .getByLabel('Notatki', { exact: true })
    .fill('Zmiana stanowiska po konkretnym argumencie.')
  await page.getByLabel('Wynik debaty').selectOption('partial')
  await page.getByRole('button', { name: 'Zapisz notatki' }).click()
  await expect(page.getByText('Zapisano', { exact: true })).toBeVisible()
  const firstMessage = page.getByTestId('public-message').first()
  await firstMessage.locator('.message-details > summary').click()
  await firstMessage.locator('.reasoning-details > summary').click()
  await expect(firstMessage.locator('.reasoning-details pre')).toContainText('Testowy materiał')
  const id = page.url().split('/').at(-1)
  const exported = await page.request.get(`/api/debates/${id}/export`)
  const data = await exported.json()
  expect(data.messages).toHaveLength(4)
  expect(data.attempts).toHaveLength(4)
  expect(data.attempts[0].request.reasoning_effort).toBe('low')
  expect(data.annotations.outcome).toBe('partial')
  expect(data.annotations.notes).toContain('Zmiana stanowiska')
  expect(JSON.stringify(data.attempts[1].request)).not.toContain('Testowy materiał')
  await page.screenshot({ path: testInfo.outputPath('conversation.png'), fullPage: true })
  const download = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Eksport JSON', exact: true }).click()
  expect((await download).suggestedFilename()).toMatch(/^debata-.*\.json$/)
  await page.getByRole('link', { name: 'Historia debat', exact: true }).click()
  await page.getByRole('textbox', { name: 'Wyszukaj debatę' }).fill('długopis')
  await expect(
    page.getByRole('link', { name: 'Spór o pożyczony długopis', exact: true }),
  ).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('history.png'), fullPage: true })
  await page.getByRole('link', { name: 'Spór o pożyczony długopis', exact: true }).click()
  await expect(page.getByLabel('Notatki', { exact: true })).toHaveValue(
    'Zmiana stanowiska po konkretnym argumencie.',
  )
  await page.getByRole('button', { name: 'Użyj tych ustawień' }).click()
  await expect(page.getByLabel('Nazwa agenta A')).toHaveValue('Anna')
  await expect(page.getByLabel('Nazwa debaty', { exact: true })).toHaveValue(
    'Spór o pożyczony długopis',
  )
  expect(errors).toEqual([])
})

test('brak klucza oraz formularz na małym ekranie', async ({ page }, testInfo) => {
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: { api_key_configured: false, model: 'qwen/qwen3.8-27b', active_debate_id: null },
    }),
  )
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Rozpocznij debatę' })).toBeDisabled()
  await expect(page.getByText('Dodaj klucz', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Polityka migracyjna' }).click()
  await page.getByRole('button', { name: 'Podgląd instrukcji' }).click()
  await expect(page.getByRole('heading', { name: 'Instrukcje wysyłane do modelu' })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  )
  expect(overflow).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true })
})
