import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import LoginForm from './LoginForm'

describe('LoginForm', () => {
  it('validates required fields and email before submitting credentials', async () => {
    const submit = vi.fn()
    const user = userEvent.setup()
    render(<LoginForm onSubmit={submit} />)
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByText('Enter a valid email address.')).toBeVisible()
    expect(screen.getByText('Enter your password.')).toBeVisible()
    await user.type(screen.getByLabelText('Email'), 'invalid-email')
    await user.type(screen.getByLabelText('Password', { exact: true }), 'test-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(submit).not.toHaveBeenCalled()
  })

  it('submits credentials, blocks duplicate requests and clears the password after success', async () => {
    let finish!: () => void
    const submit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
    const user = userEvent.setup()
    render(<LoginForm onSubmit={submit} />)
    await user.type(screen.getByLabelText('Email'), 'operator@example.test')
    await user.type(screen.getByLabelText('Password', { exact: true }), 'test-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('button', { name: /Signing in/ })).toBeDisabled()
    expect(screen.getByLabelText('Email')).toBeDisabled()
    expect(submit).toHaveBeenCalledExactlyOnceWith({
      email: 'operator@example.test',
      password: 'test-password',
    })
    finish()
    await waitFor(() => expect(screen.getByLabelText('Password', { exact: true })).toHaveValue(''))
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('shows authentication errors and permits retry without retaining the rejected password', async () => {
    const submit = vi
      .fn()
      .mockRejectedValueOnce(new Error('Invalid email or password'))
      .mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    render(<LoginForm onSubmit={submit} />)
    await user.type(screen.getByLabelText('Email'), 'operator@example.test')
    await user.type(screen.getByLabelText('Password', { exact: true }), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Invalid email or password')).toBeVisible()
    expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('')
    await user.type(screen.getByLabelText('Password', { exact: true }), 'correct-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2))
    expect(screen.queryByText('Invalid email or password')).not.toBeInTheDocument()
  })
})
