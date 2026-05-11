import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import AreasPage from './pages/AreasPage.jsx'
import AreaDetailPage from './pages/AreaDetailPage.jsx'

export default function App() {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/areas" replace />} />
          <Route path="areas" element={<AreasPage />} />
          <Route path="areas/:id" element={<AreaDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
