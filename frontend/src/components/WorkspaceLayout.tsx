import { useState } from 'react'
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import {
  Button,
  Content,
  Header,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderName,
  SideNav,
  SideNavItems,
  SideNavLink,
  SkipToContent,
} from '@carbon/react'
import { DataBase, Logout } from '@carbon/icons-react'
import { collectionKeys, collections } from '../config/collections'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../services/http'
import ErrorNotice from './ErrorNotice'

export default function WorkspaceLayout() {
  const { session, signOut } = useAuth()
  const location = useLocation()
  const [navOpen, setNavOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState('')

  if (!session)
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />

  async function logout() {
    setSigningOut(true)
    setError('')
    try {
      await signOut()
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <>
      <Header aria-label="MyoControl">
        <SkipToContent href="#main-content" />
        <HeaderMenuButton
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          isActive={navOpen}
          onClick={() => setNavOpen((value) => !value)}
        />
        <HeaderName as={Link} to="/experiments" prefix="" onClick={() => setNavOpen(false)}>
          MyoControl
        </HeaderName>
        <HeaderGlobalBar className="account-bar">
          <span className="operator-name">{session.operator.display_name}</span>
          <Button kind="ghost" size="lg" renderIcon={Logout} onClick={logout} disabled={signingOut}>
            {signingOut ? 'Signing out…' : 'Sign out'}
          </Button>
        </HeaderGlobalBar>
        <SideNav
          aria-label="Research navigation"
          expanded={navOpen}
          onToggle={(_, value?: boolean) => {
            if (value !== undefined) setNavOpen(value)
          }}
          onOverlayClick={() => setNavOpen(false)}
          onSideNavBlur={() => setNavOpen(false)}
        >
          <SideNavItems>
            <SideNavLink
              as={Link}
              to="/recordings"
              large
              renderIcon={DataBase}
              isActive={location.pathname.startsWith('/recordings')}
              onClick={() => setNavOpen(false)}
            >
              Recordings
            </SideNavLink>
            {collectionKeys.map((key) => {
              const item = collections[key]
              return (
                <SideNavLink
                  key={key}
                  as={Link}
                  to={item.path}
                  large
                  renderIcon={item.icon}
                  isActive={location.pathname.startsWith(item.path)}
                  onClick={() => setNavOpen(false)}
                >
                  {item.name}
                </SideNavLink>
              )
            })}
          </SideNavItems>
        </SideNav>
      </Header>
      <Content id="main-content" className="cloud-content">
        <div className="workspace-content">
          {error && <ErrorNotice title="Could not sign out" message={error} />}
          <Outlet />
        </div>
      </Content>
    </>
  )
}
