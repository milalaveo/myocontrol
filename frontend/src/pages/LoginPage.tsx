import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  Header,
  HeaderName,
  InlineNotification,
  Layer,
  SkipToContent,
  Stack,
  Tile,
} from '@carbon/react'
import { ChartEvaluation, Chemistry, MachineLearningModel } from '@carbon/icons-react'
import LoginForm from '../components/LoginForm'
import { useAuth } from '../context/AuthContext'
import type { Credentials } from '../types/cloud'

export default function LoginPage() {
  const { session, notice, signIn } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const from = (location.state as { from?: string } | null)?.from
  const destination =
    from && /^\/(experiments|models|results)(\/|\?|$)/.test(from) ? from : '/experiments'

  if (session) return <Navigate to={destination} replace />

  async function submit(credentials: Credentials) {
    await signIn(credentials)
    navigate(destination, { replace: true })
  }

  return (
    <>
      <Header aria-label="MyoControl">
        <SkipToContent href="#main-content" />
        <HeaderName href="/login" prefix="">
          MyoControl
        </HeaderName>
      </Header>
      <main id="main-content" className="login-page">
        <section className="login-intro">
          <span className="eyebrow">MYOCONTROL / CLOUD</span>
          <h1>
            Your research,
            <br />
            in one workspace.
          </h1>
          <p>Explore your experiments, published models and evaluation results.</p>
          <div className="login-topics">
            <Chemistry size={24} />
            <span>Experiments</span>
            <MachineLearningModel size={24} />
            <span>Models</span>
            <ChartEvaluation size={24} />
            <span>Results</span>
          </div>
        </section>
        <Tile className="login-panel">
          <Layer>
            <Stack gap={7}>
              <div>
                <h2>Sign in</h2>
                <p className="supporting-text">Use your MyoControl operator account.</p>
              </div>
              {notice && (
                <InlineNotification
                  kind="info"
                  title="Sign in required"
                  subtitle={notice}
                  hideCloseButton
                  lowContrast
                />
              )}
              <LoginForm onSubmit={submit} />
            </Stack>
          </Layer>
        </Tile>
      </main>
    </>
  )
}
