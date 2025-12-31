import { MapContainer, TileLayer, Polygon, Marker, Popup, useMap } from 'react-leaflet'
import { LatLngExpression } from 'leaflet'
import { useEffect, useMemo } from 'react'
import { School, FilterState } from '../types'
import { schools } from '../data/schools'
import './SchoolMap.css'
import L from 'leaflet'

// Fix for default marker icon in React-Leaflet
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});

L.Marker.prototype.options.icon = DefaultIcon;

interface SchoolMapProps {
  filters: FilterState;
  selectedSchoolId: string | null;
  setSelectedSchoolId: (id: string | null) => void;
}

function MapUpdater({ selectedSchool }: { selectedSchool: School | null }) {
  const map = useMap()

  useEffect(() => {
    if (selectedSchool) {
      map.setView([selectedSchool.latitude, selectedSchool.longitude], 14, {
        animate: true
      })
    }
  }, [selectedSchool, map])

  return null
}

function SchoolMap({ filters, selectedSchoolId, setSelectedSchoolId }: SchoolMapProps) {
  const brisbaneCenter: LatLngExpression = [-27.4698, 153.0251]

  const filteredSchools = useMemo(() => {
    return schools.filter(school => {
      // Only show secondary schools
      if (school.level !== 'Secondary' && school.level !== 'Combined') {
        return false
      }

      // Filter by school type
      if (!filters.schoolType.includes(school.type)) {
        return false
      }

      // Filter by ICSEA
      if (filters.minICSEA && school.icsea && school.icsea < filters.minICSEA) {
        return false
      }
      if (filters.maxICSEA && school.icsea && school.icsea > filters.maxICSEA) {
        return false
      }

      // Filter by search query
      if (filters.searchQuery) {
        const query = filters.searchQuery.toLowerCase()
        return (
          school.name.toLowerCase().includes(query) ||
          school.suburb.toLowerCase().includes(query)
        )
      }

      return true
    })
  }, [filters])

  const selectedSchool = selectedSchoolId
    ? schools.find(s => s.id === selectedSchoolId) || null
    : null

  const getColorByICSEA = (icsea?: number): string => {
    if (!icsea) return '#999999'
    if (icsea >= 1100) return '#2E7D32' // Dark green - high socio-educational advantage
    if (icsea >= 1050) return '#66BB6A' // Green
    if (icsea >= 1000) return '#FFA726' // Orange - average
    if (icsea >= 950) return '#FF7043' // Deep orange
    return '#E53935' // Red - low socio-educational advantage
  }

  return (
    <div className="map-container">
      <MapContainer
        center={brisbaneCenter}
        zoom={11}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <MapUpdater selectedSchool={selectedSchool} />

        {filteredSchools.map(school => (
          <div key={school.id}>
            {school.catchmentBoundary && (
              <Polygon
                positions={
                  school.catchmentBoundary.type === 'Polygon'
                    ? school.catchmentBoundary.coordinates[0].map(
                        coord => [coord[1], coord[0]] as LatLngExpression
                      )
                    : school.catchmentBoundary.coordinates.flatMap(poly =>
                        poly[0].map(coord => [coord[1], coord[0]] as LatLngExpression)
                      )
                }
                pathOptions={{
                  color: getColorByICSEA(school.icsea),
                  fillColor: getColorByICSEA(school.icsea),
                  fillOpacity: selectedSchoolId === school.id ? 0.4 : 0.2,
                  weight: selectedSchoolId === school.id ? 3 : 2
                }}
                eventHandlers={{
                  click: () => setSelectedSchoolId(school.id)
                }}
              />
            )}
            <Marker
              position={[school.latitude, school.longitude]}
              eventHandlers={{
                click: () => setSelectedSchoolId(school.id)
              }}
            >
              <Popup>
                <div className="school-popup">
                  <h3>{school.name}</h3>
                  <p><strong>Type:</strong> {school.type}</p>
                  <p><strong>Suburb:</strong> {school.suburb}</p>
                  {school.icsea && (
                    <p><strong>ICSEA:</strong> {school.icsea}</p>
                  )}
                  {school.naplanAverage && (
                    <p><strong>NAPLAN Average:</strong> {school.naplanAverage.toFixed(1)}</p>
                  )}
                  {school.enrollment && (
                    <p><strong>Enrollment:</strong> {school.enrollment}</p>
                  )}
                </div>
              </Popup>
            </Marker>
          </div>
        ))}
      </MapContainer>

      <div className="legend">
        <h4>ICSEA Score</h4>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#2E7D32' }}></span>
          <span>1100+ (Very High)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#66BB6A' }}></span>
          <span>1050-1099 (High)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#FFA726' }}></span>
          <span>1000-1049 (Average)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#FF7043' }}></span>
          <span>950-999 (Below Average)</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#E53935' }}></span>
          <span>&lt;950 (Low)</span>
        </div>
      </div>
    </div>
  )
}

export default SchoolMap
