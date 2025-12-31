import { MapContainer, TileLayer, Polygon, Marker, Popup, useMap } from 'react-leaflet'
import { LatLngExpression } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { School, FilterState, CatchmentFeature } from '../types'
import { schools } from '../data/schools'
import { catchments, catchmentMetadata } from '../data/catchmentLoader'
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
  const [selectedCatchment, setSelectedCatchment] = useState<string | null>(null)

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

  // Convert catchment coordinates to Leaflet format
  const getCatchmentPositions = (catchment: CatchmentFeature): LatLngExpression[][] => {
    const geometry = catchment.geometry
    if (geometry.type === 'Polygon') {
      return geometry.coordinates.map(ring =>
        ring.map(coord => [coord[1], coord[0]] as LatLngExpression)
      )
    } else {
      // MultiPolygon - flatten to array of rings
      return geometry.coordinates.flatMap(polygon =>
        polygon.map(ring =>
          ring.map(coord => [coord[1], coord[0]] as LatLngExpression)
        )
      )
    }
  }

  // Generate consistent color for catchment based on name
  const getCatchmentColor = (name: string): string => {
    let hash = 0
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash)
    }
    const h = hash % 360
    return `hsl(${h}, 60%, 50%)`
  }

  const selectedSchool = selectedSchoolId
    ? schools.find(s => s.id === selectedSchoolId) || null
    : null

  
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

        {/* Render official catchment boundaries */}
        {filters.showCatchments && catchments.map(catchment => {
          const positions = getCatchmentPositions(catchment)
          const name = catchment.properties.name
          const color = getCatchmentColor(name)
          const isSelected = selectedCatchment === name

          return positions.map((ring, idx) => (
            <Polygon
              key={`${name}-${idx}`}
              positions={ring}
              pathOptions={{
                color: color,
                fillColor: color,
                fillOpacity: isSelected ? 0.4 : 0.15,
                weight: isSelected ? 3 : 1
              }}
              eventHandlers={{
                click: () => setSelectedCatchment(isSelected ? null : name),
                mouseover: (e) => {
                  e.target.setStyle({ fillOpacity: 0.35, weight: 2 })
                },
                mouseout: (e) => {
                  e.target.setStyle({
                    fillOpacity: isSelected ? 0.4 : 0.15,
                    weight: isSelected ? 3 : 1
                  })
                }
              }}
            >
              <Popup>
                <div className="catchment-popup">
                  <h3>{name}</h3>
                  <p><strong>Type:</strong> State School Catchment</p>
                  <p><strong>Years:</strong> 11-12 (Senior Secondary)</p>
                  <p className="data-source">
                    <em>Source: {catchmentMetadata.description}</em>
                  </p>
                </div>
              </Popup>
            </Polygon>
          ))
        })}

        {/* Render school markers */}
        {filteredSchools.map(school => (
          <Marker
            key={school.id}
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
        ))}
      </MapContainer>

      <div className="legend">
        <h4>Catchment Areas</h4>
        <p className="legend-info">
          {catchments.length} state school catchment boundaries<br />
          (Years 11-12 Senior Secondary)
        </p>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#888', opacity: 0.3 }}></span>
          <span>Click catchment for details</span>
        </div>
        <p className="legend-source">
          Data: QLD Open Data Portal<br />
          Updated: 2025
        </p>
      </div>
    </div>
  )
}

export default SchoolMap
