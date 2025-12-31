import { useState } from 'react'
import SchoolMap from './components/SchoolMap'
import Sidebar from './components/Sidebar'
import { FilterState } from './types'
import './App.css'

function App() {
  const [filters, setFilters] = useState<FilterState>({
    schoolType: ['State', 'Catholic', 'Independent'],
    searchQuery: '',
    showCatchments: true
  })

  const [selectedSchoolName, setSelectedSchoolName] = useState<string | null>(null)

  return (
    <div className="app">
      <Sidebar
        filters={filters}
        setFilters={setFilters}
        selectedSchoolName={selectedSchoolName}
      />
      <SchoolMap
        filters={filters}
        selectedSchoolName={selectedSchoolName}
        setSelectedSchoolName={setSelectedSchoolName}
      />
    </div>
  )
}

export default App
