import { FilterState } from '../types'
import { schools } from '../data/schools'
import './Sidebar.css'

interface SidebarProps {
  filters: FilterState;
  setFilters: (filters: FilterState) => void;
  selectedSchoolId: string | null;
}

function Sidebar({ filters, setFilters, selectedSchoolId }: SidebarProps) {
  const selectedSchool = selectedSchoolId
    ? schools.find(s => s.id === selectedSchoolId)
    : null

  const handleTypeToggle = (type: string) => {
    const newTypes = filters.schoolType.includes(type)
      ? filters.schoolType.filter(t => t !== type)
      : [...filters.schoolType, type]
    setFilters({ ...filters, schoolType: newTypes })
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>Brisbane Schools</h1>
        <p className="subtitle">Secondary School Catchments & Rankings</p>
      </div>

      <div className="sidebar-content">
        <div className="filter-section">
          <h3>Search</h3>
          <input
            type="text"
            placeholder="Search by school or suburb..."
            value={filters.searchQuery}
            onChange={(e) => setFilters({ ...filters, searchQuery: e.target.value })}
            className="search-input"
          />
        </div>

        <div className="filter-section">
          <h3>School Type</h3>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filters.schoolType.includes('State')}
              onChange={() => handleTypeToggle('State')}
            />
            <span>State Schools</span>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filters.schoolType.includes('Catholic')}
              onChange={() => handleTypeToggle('Catholic')}
            />
            <span>Catholic Schools</span>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filters.schoolType.includes('Independent')}
              onChange={() => handleTypeToggle('Independent')}
            />
            <span>Independent Schools</span>
          </label>
        </div>

        <div className="filter-section">
          <h3>Display Options</h3>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filters.showCatchments}
              onChange={() => setFilters({ ...filters, showCatchments: !filters.showCatchments })}
            />
            <span>Show Catchment Boundaries</span>
          </label>
        </div>

        <div className="filter-section">
          <h3>ICSEA Range</h3>
          <div className="range-inputs">
            <input
              type="number"
              placeholder="Min"
              value={filters.minICSEA || ''}
              onChange={(e) => setFilters({
                ...filters,
                minICSEA: e.target.value ? parseInt(e.target.value) : undefined
              })}
              className="range-input"
            />
            <span>to</span>
            <input
              type="number"
              placeholder="Max"
              value={filters.maxICSEA || ''}
              onChange={(e) => setFilters({
                ...filters,
                maxICSEA: e.target.value ? parseInt(e.target.value) : undefined
              })}
              className="range-input"
            />
          </div>
          <p className="help-text">ICSEA average is 1000</p>
        </div>

        {selectedSchool && (
          <div className="school-details">
            <h3>Selected School</h3>
            <h2>{selectedSchool.name}</h2>
            <div className="detail-row">
              <span className="label">Type:</span>
              <span className="value">{selectedSchool.type}</span>
            </div>
            <div className="detail-row">
              <span className="label">Address:</span>
              <span className="value">{selectedSchool.address}, {selectedSchool.suburb} {selectedSchool.postcode}</span>
            </div>
            {selectedSchool.icsea && (
              <div className="detail-row">
                <span className="label">ICSEA:</span>
                <span className="value">{selectedSchool.icsea}</span>
              </div>
            )}
            {selectedSchool.naplanAverage && (
              <div className="detail-row">
                <span className="label">NAPLAN Average:</span>
                <span className="value">{selectedSchool.naplanAverage.toFixed(1)}</span>
              </div>
            )}
            {selectedSchool.enrollment && (
              <div className="detail-row">
                <span className="label">Enrollment:</span>
                <span className="value">{selectedSchool.enrollment}</span>
              </div>
            )}
            {selectedSchool.website && (
              <div className="detail-row">
                <a
                  href={selectedSchool.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="website-link"
                >
                  Visit Website
                </a>
              </div>
            )}
          </div>
        )}

        <div className="info-section">
          <h4>About ICSEA</h4>
          <p className="info-text">
            The Index of Community Socio-Educational Advantage (ICSEA) is a scale that enables
            meaningful comparisons of test achievement by students in schools across Australia.
            The average ICSEA score is 1000.
          </p>
        </div>
      </div>
    </div>
  )
}

export default Sidebar
