import { ArrowRight, Database, FlaskConical } from 'lucide-react'
import { Link } from 'react-router-dom'
import { count, useResource, type Workspace } from './api'
import { Notice, PageHeading, Waiting } from './components'

export function DatasetPage() {
  const workspace = useResource<Workspace>('/workspace')
  const data = workspace.value?.dataset
  return <>
    <PageHeading title="About the data" subtitle="Meet the fictional retailer behind each investigation." />
    {workspace.error && <Notice>{workspace.error}</Notice>}
    {!data && !workspace.error && <Waiting label="Loading the dataset…" />}
    {data && <>
      <section className="panel dataset-intro">
        <span className="icon-tile"><FlaskConical size={24} aria-hidden /></span>
        <div><h2>Northstar Shop</h2><p>A fictional retailer selling through its website and mobile app.
          These records describe shoppers starting checkout, paying for orders, and contacting support.
          Software releases and feature rollouts help explain when the shopping experience changed.</p>
          <p>Every record is synthetic and reproducible. The scenarios include healthy shopping periods,
            payment failures, traffic shifts, and incomplete data.</p></div>
      </section>
      <div className="dataset-tables">{data.tables.map((table) => <section className="panel" key={table.name}>
        <Database size={19} aria-hidden /><div><h3>{table.name}</h3><p>{table.purpose}</p></div>
        <span>{count(table.rows)} records</span>
      </section>)}</div>
      <section className="panel dataset-story"><h2>One incident, several clues</h2>
        <p>In the checkout example, shoppers start checkout as often as before, but fewer finish.
          Payment records show more authentication timeouts, a mobile update went out, and support complaints increased.
          AgentFlow checks whether these clues agree, cites the records, and prepares an assessment for you to review.</p>
        <Link className="button primary" to="/new?scenario=checkout-conversion-drop">Investigate this case <ArrowRight size={16} aria-hidden /></Link>
      </section>
    </>}
  </>
}
