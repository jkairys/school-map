import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import AreasPage from './pages/AreasPage.jsx'
import AreaDetailPage from './pages/AreaDetailPage.jsx'
import SuburbDetailPage from './pages/SuburbDetailPage.jsx'
import PropertyDetailPage from './pages/PropertyDetailPage.jsx'
import ListingDetailPage from './pages/ListingDetailPage.jsx'
import RunDetailPage from './pages/RunDetailPage.jsx'

export default function App() {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/areas" replace />} />
          <Route path="areas" element={<AreasPage />} />
          <Route path="areas/:id" element={<AreaDetailPage />} />
          <Route path="suburbs/:id" element={<SuburbDetailPage />} />
          <Route path="properties/:id" element={<PropertyDetailPage />} />
          <Route path="listings/:id" element={<ListingDetailPage />} />
          <Route path="runs/:id" element={<RunDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
