import { GlobalTheme } from '@carbon/react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import WorkspaceLayout from './components/WorkspaceLayout'
import { AuthProvider } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import RegistryPage from './pages/RegistryPage'
import RecordingsPage from './pages/RecordingsPage'

export default function App() {
  return (
    <ErrorBoundary>
      <GlobalTheme theme="white">
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<WorkspaceLayout />}>
                <Route path="/recordings" element={<RecordingsPage />} />
                <Route
                  path="/experiments"
                  element={<RegistryPage key="runs" collection="runs" />}
                />
                <Route
                  path="/experiments/:id"
                  element={<RegistryPage key="run-detail" collection="runs" />}
                />
                <Route path="/models" element={<RegistryPage key="models" collection="models" />} />
                <Route
                  path="/models/:id"
                  element={<RegistryPage key="model-detail" collection="models" />}
                />
                <Route
                  path="/results"
                  element={<RegistryPage key="results" collection="results" />}
                />
                <Route
                  path="/results/:id"
                  element={<RegistryPage key="result-detail" collection="results" />}
                />
              </Route>
              <Route path="*" element={<Navigate to="/experiments" replace />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </GlobalTheme>
    </ErrorBoundary>
  )
}
