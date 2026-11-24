import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Form, InlineLoading, PasswordInput, Stack, TextInput } from '@carbon/react'
import { ArrowRight } from '@carbon/icons-react'
import { errorMessage } from '../services/http'
import type { Credentials } from '../types/cloud'
import ErrorNotice from './ErrorNotice'

export default function LoginForm({
  onSubmit,
}: {
  onSubmit: (credentials: Credentials) => Promise<void>
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [validation, setValidation] = useState<{ email?: string; password?: string }>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const errors = {
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
        ? undefined
        : 'Enter a valid email address.',
      password: password.length ? undefined : 'Enter your password.',
    }
    setValidation(errors)
    setError('')
    if (errors.email || errors.password) return
    setBusy(true)
    try {
      await onSubmit({ email: email.trim(), password })
      setPassword('')
    } catch (cause) {
      setError(errorMessage(cause))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Form onSubmit={submit} noValidate aria-label="Operator sign in">
      <Stack gap={6}>
        <TextInput
          id="email"
          name="email"
          type="email"
          labelText="Email"
          autoComplete="username"
          required
          maxLength={320}
          value={email}
          onChange={(event) => {
            setEmail(event.target.value)
            setValidation((current) => ({ ...current, email: undefined }))
          }}
          invalid={!!validation.email}
          invalidText={validation.email}
          disabled={busy}
        />
        <PasswordInput
          id="password"
          name="password"
          labelText="Password"
          autoComplete="current-password"
          required
          maxLength={1024}
          value={password}
          onChange={(event) => {
            setPassword(event.target.value)
            setValidation((current) => ({ ...current, password: undefined }))
          }}
          invalid={!!validation.password}
          invalidText={validation.password}
          disabled={busy}
        />
        {error && <ErrorNotice title="Sign in failed" message={error} />}
        <Button type="submit" renderIcon={ArrowRight} disabled={busy} className="login-submit">
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>
        {busy && <InlineLoading description="Verifying your account…" />}
      </Stack>
    </Form>
  )
}
