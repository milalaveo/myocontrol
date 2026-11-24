import { Component, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { Button, Theme } from '@carbon/react'
import App from './App'
import './styles.scss'

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <div className="fatal">
        <h1>Workspace could not be displayed</h1>
        <p>Saved recordings remain in your local profile.</p>
        <Button onClick={() => location.reload()}>Reload workspace</Button>
      </div>
    ) : (
      this.props.children
    )
  }
}
createRoot(document.getElementById('root')!).render(
  <Theme theme="white">
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </Theme>,
)
