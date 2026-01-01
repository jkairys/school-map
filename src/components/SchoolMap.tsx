import { MapContainer, TileLayer, Polygon, CircleMarker, Popup, Tooltip, useMap } from 'react-leaflet'
import { LatLngExpression } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { FilterState, CatchmentFeature } from '../types'
import { schoolSites, SchoolSite } from '../data/schoolSitesLoader'
import { catchments, catchmentMetadata } from '../data/catchmentLoader'
import './SchoolMap.css'

interface SchoolMapProps {
  filters: FilterState;
  selectedSchoolName: string | null;
  setSelectedSchoolName: (name: string | null) => void;
}

function MapUpdater({ selectedSchool }: { selectedSchool: SchoolSite | null }) {
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

function ZoomTracker({ onZoomChange }: { onZoomChange: (zoom: number) => void }) {
  const map = useMap()

  useEffect(() => {
    const updateZoom = () => {
      const zoom = map.getZoom()
      onZoomChange(zoom)
      // Set CSS variable for font scaling
      const container = map.getContainer()
      container.style.setProperty('--label-font-size', `${getLabelFontSize(zoom)}px`)
    }

    updateZoom()
    map.on('zoomend', updateZoom)
    return () => {
      map.off('zoomend', updateZoom)
    }
  }, [map, onZoomChange])

  return null
}

// Calculate label font size based on zoom level
function getLabelFontSize(zoom: number): number {
  // Scale from 8px at zoom 9 to 13px at zoom 15
  const minZoom = 9
  const maxZoom = 15
  const minSize = 8
  const maxSize = 13

  const clampedZoom = Math.max(minZoom, Math.min(maxZoom, zoom))
  const ratio = (clampedZoom - minZoom) / (maxZoom - minZoom)
  return minSize + ratio * (maxSize - minSize)
}

function SchoolMap({ filters, selectedSchoolName, setSelectedSchoolName }: SchoolMapProps) {
  const brisbaneCenter: LatLngExpression = [-27.4698, 153.0251]
  const [selectedCatchment, setSelectedCatchment] = useState<string | null>(null)
  const [zoomLevel, setZoomLevel] = useState(11)

  // Calculate circle radius based on zoom level
  const getCircleRadius = (zoom: number): number => {
    // Scale from 3px at zoom 9 to 10px at zoom 15
    const minZoom = 9
    const maxZoom = 15
    const minRadius = 3
    const maxRadius = 10

    const clampedZoom = Math.max(minZoom, Math.min(maxZoom, zoom))
    const ratio = (clampedZoom - minZoom) / (maxZoom - minZoom)
    return minRadius + ratio * (maxRadius - minRadius)
  }

  const filteredSchools = useMemo(() => {
    return schoolSites.filter(school => {
      // Filter by search query
      if (filters.searchQuery) {
        const query = filters.searchQuery.toLowerCase()
        return school.name.toLowerCase().includes(query)
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

  const selectedSchool = selectedSchoolName
    ? schoolSites.find(s => s.name === selectedSchoolName) || null
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
        <ZoomTracker onZoomChange={setZoomLevel} />

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
          <CircleMarker
            key={school.name}
            center={[school.latitude, school.longitude]}
            radius={getCircleRadius(zoomLevel)}
            pathOptions={{
              fillColor: '#3b82f6',
              fillOpacity: 1,
              stroke: false
            }}
            eventHandlers={{
              click: () => setSelectedSchoolName(school.name)
            }}
          >
            <Tooltip
              permanent
              direction="right"
              offset={[8, 0]}
              className="school-label"
            >
              {school.name.replace(' SHS', '').replace(' State College', '').replace(' State Secondary College', '')}
            </Tooltip>
            <Popup>
              <div className="school-popup">
                <h3>{school.name}</h3>
                <p><strong>Type:</strong> State School</p>
                <p><strong>Years:</strong> 11-12 (Senior Secondary)</p>
                {school.code && (
                  <p><strong>School Code:</strong> {school.code}</p>
                )}
              </div>
            </Popup>
          </CircleMarker>
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
