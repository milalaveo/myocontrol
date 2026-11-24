import { Component } from 'react'
import type { ReactNode } from 'react'
import { Button, GlobalTheme, Tile } from '@carbon/react'

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed)
      return (
        <GlobalTheme theme="white">
          <main className="fatal-error">
            <Tile>
              <h1>The workspace could not be displayed</h1>
              <p>Reload the application to recover. You may need to sign in again.</p>
              <Button onClick={() => window.location.reload()}>Reload application</Button>
            </Tile>
          </main>
        </GlobalTheme>
      )
    return this.props.children
  }
}
