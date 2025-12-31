import { useState } from 'react'
import SchoolMap from './components/SchoolMap'
import Sidebar from './components/Sidebar'
import { FilterState } from './types'
import './App.css'

function App() {
  const [filters, setFilters] = useState<FilterState>({
    schoolType: ['State', 'Catholic', 'Independent'],
    searchQuery: ''
  })

  const [selectedSchoolId, setSelectedSchoolId] = useState<string | null>(null)

  return (
    <div className="app">
      <Sidebar
        filters={filters}
        setFilters={setFilters}
        selectedSchoolId={selectedSchoolId}
      />
      <SchoolMap
        filters={filters}
        selectedSchoolId={selectedSchoolId}
        setSelectedSchoolId={setSelectedSchoolId}
      />
    </div>
  )
}

export default App
