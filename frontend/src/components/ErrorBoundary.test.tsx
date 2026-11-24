import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

describe('ErrorBoundary', () => {
  it('replaces a rendering failure with an actionable recovery screen', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    function BrokenComponent(): never {
      throw new Error('Render failed')
    }
    render(
      <ErrorBoundary>
        <BrokenComponent />
      </ErrorBoundary>,
    )
    expect(
      screen.getByRole('heading', { name: 'The workspace could not be displayed' }),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Reload application' })).toBeVisible()
    expect(screen.queryByText('Render failed')).not.toBeInTheDocument()
  })
})
