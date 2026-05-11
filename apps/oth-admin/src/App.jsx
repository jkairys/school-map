import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Construction } from 'lucide-react'
import Layout from './components/Layout.jsx'
import AreasPage from './pages/AreasPage.jsx'
import AreaDetailPage from './pages/AreaDetailPage.jsx'
import SuburbDetailPage from './pages/SuburbDetailPage.jsx'

/**
 * Minimal placeholder for pages that haven't been implemented yet.
 * Accepts an optional label prop to identify which future slice owns it.
 */
function PlaceholderPage({ label }) {
  const params = useParams()
  const id = params.id ?? null
  return (
    <div className="flex flex-col items-center justify-center py-20 text-neutral-400">
      <Construction size={40} className="mb-3 opacity-30" />
      <p className="text-sm font-medium text-neutral-500">{label} — coming soon</p>
      {id && <p className="text-xs mt-1 text-neutral-400">ID: {id}</p>}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/areas" replace />} />
          <Route path="areas" element={<AreasPage />} />
          <Route path="areas/:id" element={<AreaDetailPage />} />
          <Route path="suburbs/:id" element={<SuburbDetailPage />} />
          {/* Placeholder routes — implemented in future slices */}
          <Route path="properties/:id" element={<PlaceholderPage label="Property detail — slice 11" />} />
          <Route path="listings/:id" element={<PlaceholderPage label="Listing detail — slice 11" />} />
          <Route path="runs/:id" element={<PlaceholderPage label="Run detail — slice 12" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
