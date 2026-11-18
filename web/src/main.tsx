import '@fontsource-variable/inter'
import './styles.css'
import './experience.css'
import './responsive.css'
import { Activity, Cable, Database, FlaskConical, LayoutGrid, Plus, Workflow } from 'lucide-react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { DatasetPage } from './dataset'
import { Empty } from './components'
import { ConnectionsPage, EvaluationsPage } from './evaluation'
import { NewInvestigation, Overview } from './overview'
import { RunDetail } from './run'

const navigation = [
  { path: '/', name: 'Overview', icon: LayoutGrid },
  { path: '/new', name: 'New investigation', icon: Plus },
  { path: '/evaluations', name: 'Evaluations', icon: Activity },
  { path: '/data', name: 'About the data', icon: Database },
  { path: '/connections', name: 'Connections', icon: Cable },
]

function Shell() {
  const { pathname } = useLocation()
  const active = navigation.find(({ path }) => path !== '/' && pathname.startsWith(path))
  const section = pathname.startsWith('/investigations/') ? 'Investigation detail' : active?.name ?? 'Overview'
  return <div className="shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-icon"><Workflow size={23} aria-hidden /></span>AgentFlow</Link>
      <nav aria-label="Workspace">{navigation.map(({ path, name, icon: Icon }) =>
        <NavLink to={path} end={path === '/'} key={path}><Icon size={18} aria-hidden /><span>{name}</span></NavLink>,
      )}</nav>
      <div className="workspace"><span className="workspace-icon"><FlaskConical size={17} aria-hidden /></span>
        <div><strong>Northstar Shop</strong><span>Synthetic dataset</span></div>
      </div>
    </aside>
    <div className="content">
      <header className="topbar"><span>Workspace<span className="breadcrumb-slash">/</span><strong>{section}</strong></span>
        <Link to="/connections" className="local-link"><Cable size={15} aria-hidden /> Service status</Link>
      </header>
      <main id="main" className="page">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/data" element={<DatasetPage />} />
          <Route path="/new" element={<NewInvestigation />} />
          <Route path="/investigations/:id" element={<RunDetail />} />
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/evaluations/:id" element={<EvaluationsPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="*" element={<Empty title="Page unavailable" text="Open the workspace to continue." action={<Link to="/" className="button primary">Overview</Link>} />} />
        </Routes>
      </main>
    </div>
  </div>
}

const container = document.getElementById('root')
if (!container) throw new Error('App root is missing.')
createRoot(container).render(<StrictMode><BrowserRouter><Shell /></BrowserRouter></StrictMode>)
