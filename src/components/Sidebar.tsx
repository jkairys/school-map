import { FilterState } from '../types'
import { schoolSites } from '../data/schoolSitesLoader'
import './Sidebar.css'

interface SidebarProps {
  filters: FilterState;
  setFilters: (filters: FilterState) => void;
  selectedSchoolName: string | null;
}

function Sidebar({ filters, setFilters, selectedSchoolName }: SidebarProps) {
  const selectedSchool = selectedSchoolName
    ? schoolSites.find(s => s.name === selectedSchoolName)
    : null

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>Brisbane Schools</h1>
        <p className="subtitle">Senior Secondary School Catchments</p>
      </div>

      <div className="sidebar-content">
        <div className="filter-section">
          <h3>Search</h3>
          <input
            type="text"
            placeholder="Search by school name..."
            value={filters.searchQuery}
            onChange={(e) => setFilters({ ...filters, searchQuery: e.target.value })}
            className="search-input"
          />
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
          <p className="stats-info">
            <strong>{schoolSites.length}</strong> state schools<br />
            Years 11-12 (Senior Secondary)
          </p>
        </div>

        {selectedSchool && (
          <div className="school-details">
            <h3>Selected School</h3>
            <h2>{selectedSchool.name}</h2>
            <div className="detail-row">
              <span className="label">Type:</span>
              <span className="value">State School</span>
            </div>
            <div className="detail-row">
              <span className="label">Years:</span>
              <span className="value">11-12 (Senior Secondary)</span>
            </div>
            {selectedSchool.code && (
              <div className="detail-row">
                <span className="label">School Code:</span>
                <span className="value">{selectedSchool.code}</span>
              </div>
            )}
            <div className="detail-row">
              <span className="label">Location:</span>
              <span className="value">{selectedSchool.latitude.toFixed(4)}, {selectedSchool.longitude.toFixed(4)}</span>
            </div>
          </div>
        )}

        <div className="info-section">
          <h4>About This Data</h4>
          <p className="info-text">
            School locations and catchment boundaries are sourced from the Queensland Government
            Open Data Portal. Catchments show the areas for Years 11-12 (Senior Secondary) state schools.
          </p>
        </div>
      </div>
    </div>
  )
}

export default Sidebar
