import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import RegistryDetails from './RegistryDetails'

describe('RegistryDetails', () => {
  it('renders metrics, missing values, booleans and complete identifiers', () => {
    render(
      <RegistryDetails
        detail={{
          id: 'complete-registry-id',
          accuracy: 0.925,
          rest_false_activation_rate: null,
          neutral_confirmed: false,
        }}
      />,
    )
    expect(screen.getByText('complete-registry-id')).toBeVisible()
    expect(screen.getByText('92.50%')).toBeVisible()
    expect(screen.getByText('N/A')).toBeVisible()
    expect(screen.getByText('No')).toBeVisible()
  })

  it('reveals the feature contract on demand and displays actual versus predicted counts', async () => {
    const user = userEvent.setup()
    render(
      <RegistryDetails
        detail={{
          feature_contract: { version: 'four-channel-v1' },
          confusion_counts: [{ actual_class: 'rest', predicted_class: 'fist', count: 3 }],
        }}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'Feature contract' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/four-channel-v1/)).toBeVisible()
    expect(screen.getByRole('table', { name: 'Confusion counts' })).toHaveTextContent('RestFist3')
  })
})
