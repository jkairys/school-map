import React, { useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, GeoJSON, useMap, Pane } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix for default marker icons in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

import { getSchoolRelativeScore } from '../utils/naplanUtils';

// Component to handle zoom classes on map container
const ZoomHandler = () => {
  const map = useMap();
  useEffect(() => {
    const updateZoom = () => {
      const z = Math.round(map.getZoom());
      map.getContainer().setAttribute('data-zoom', z);
    };
    map.on('zoom', updateZoom);
    updateZoom(); // Init
    return () => map.off('zoom', updateZoom);
  }, [map]);
  return null;
};



const MapComponent = ({
  onSchoolSelect,
  selectedSchool,
  selectedCompetency,
  showCatchments,
  showSchoolLocations,
  showRailwayStations,
  schoolData,
  stateAverages
}) => {
  const [geoData, setGeoData] = useState(null);
  // schoolData and stateAverages are now props
  const [schoolSites, setSchoolSites] = useState(null);
  const [railwayStations, setRailwayStations] = useState(null);
  const [transitTimes, setTransitTimes] = useState(null);

  useEffect(() => {
    // Load Catchments
    fetch('/data/catchments.geojson')
      .then(res => res.json())
      .then(data => setGeoData(data))
      .catch(err => console.error("Error loading GeoJSON:", err));

    // NAPLAN Data is now passed in props

    // Load School Sites
    fetch('/data/school_sites.geojson')
      .then(res => res.json())
      .then(data => setSchoolSites(data))
      .catch(err => console.error("Error loading School Sites:", err));

    // Load Railway Stations
    fetch('/data/railway-station-locations.geojson')
      .then(res => res.json())
      .then(data => setRailwayStations(data))
      .catch(err => console.error("Error loading Railway Stations:", err));

    // Load Transit Times
    fetch('/data/station-transit-times.json')
      .then(res => res.json())
      .then(data => {
        // Create lookup map from station name to transit data
        const lookup = {};
        data.stations.forEach(station => {
          lookup[station.name] = station.transitToCentral;
        });
        setTransitTimes(lookup);
      })
      .catch(err => console.error("Error loading Transit Times:", err));
  }, []);

  // Helper to ensure stable function reference if needed, though simple function is fine
  const getSchoolColor = useCallback((name) => {
    if (!schoolData || !schoolData[name] || !stateAverages || !selectedCompetency) {
      // Fallback or No Data
      return '#9ca3af'; // Gray 400 (neutral for no data)
    }

    const school = schoolData[name];
    const score = getSchoolRelativeScore(school, selectedCompetency, stateAverages);

    if (score === null) return '#9ca3af';

    // Thresholds
    // < 0.95: Red
    // 0.95 - 1.0: Orange  (User: "orange for a little bit under average")
    // 1.0 - 1.05: Light Green
    // > 1.05: Dark Green

    if (score < 0.95) return '#ef4444'; // Red 500
    if (score < 1.0) return '#f97316'; // Orange 500
    if (score < 1.05) return '#86efac'; // Green 300
    return '#15803d'; // Green 700
  }, [schoolData, stateAverages, selectedCompetency]);

  // Ref to store school marker layers by name
  const markerLayersRef = React.useRef({});

  // Effect to update marker styles when selectedSchool changes
  useEffect(() => {
    // Reset all markers to default style (no border) first to be safe,
    // or just reset the previously selected one if we tracked it.
    // Iterating all is safer to ensure no artifacts.
    Object.values(markerLayersRef.current).forEach(layer => {
      const name = layer.feature.properties.name;
      const color = getSchoolColor(name);
      layer.setStyle({
        color: color, // Border same as fill (invisible border effectively) or transparent if stroke false
        fillColor: color,
        stroke: false,
        fillOpacity: 0.9
      });
    });

    if (selectedSchool && selectedSchool.name) {
      const layer = markerLayersRef.current[selectedSchool.name];
      if (layer) {
        layer.setStyle({
          stroke: true,
          color: 'black',
          weight: 3,
          fillOpacity: 1
        });
        layer.bringToFront();
      }
    }
  }, [selectedSchool, getSchoolColor]);

  const onEachFeature = useCallback((feature, layer) => {
    const { name } = feature.properties;

    layer.on({
      mouseover: (e) => {
        const layer = e.target;
        const color = getSchoolColor(name);
        layer.setStyle({
          weight: 3,
          color: 'black',
          fillColor: color,
          fillOpacity: 0.1, // Very subtle fill on hover
          opacity: 1
        });
        layer.bringToFront();
      },
      mouseout: (e) => {
        const layer = e.target;
        // Re-apply style
        layer.setStyle({
          fillColor: 'transparent',
          weight: 1.5,
          opacity: 0.6,
          color: 'black',
          fillOpacity: 0
        });
      }
    });
  }, [getSchoolColor]);

  const style = useCallback((feature) => {
    // Default style for catchments: Visible black border, no fill
    return {
      fillColor: 'transparent',
      weight: 1.5,
      opacity: 0.6,
      color: 'black',
      dashArray: '',
      fillOpacity: 0
    };
  }, []);

  const onEachSchoolSite = useCallback((feature, layer) => {
    const { name } = feature.properties;

    // Store reference to layer
    if (name) {
      markerLayersRef.current[name] = layer;
    }

    // Label with school name (Permanent)
    if (name) {
      const color = getSchoolColor(name);
      const content = `<span style="color: ${color}; text-shadow: 0 0 2px white; font-weight: bold;">${name}</span>`;

      layer.bindTooltip(content, {
        permanent: true,
        direction: 'right',
        className: 'school-site-label',
        offset: [0, 0],
        pane: 'school-sites-pane'
      });
    }

    // Click handler for selection
    layer.on('click', () => {
      if (onSchoolSelect) {
        // Helper to check if currently selected
        const isSelected = selectedSchool && selectedSchool.name === name;

        if (isSelected) {
          // Deselect
          onSchoolSelect(null);
        } else {
          // Select
          const data = schoolData ? schoolData[name] : null;
          onSchoolSelect(data ? { ...data, name } : { name });
        }
      }
    });

  }, [getSchoolColor, schoolData, selectedSchool, onSchoolSelect]);

  const pointToLayerSchoolSite = useCallback((feature, latlng) => {
    const color = getSchoolColor(feature.properties.name);

    // Colored dot
    return L.circle(latlng, {
      radius: 150,
      stroke: false,
      color: color,
      fillColor: color,
      fillOpacity: 0.9,
      pane: 'school-sites-pane'
    });
  }, [getSchoolColor]);

  const getStationColor = useCallback((stationName) => {
    if (!transitTimes || !transitTimes[stationName]) {
      return '#9ca3af'; // gray-400 for stations without transit data
    }

    const durationSeconds = transitTimes[stationName].durationSeconds;
    const durationMinutes = durationSeconds / 60;

    if (durationMinutes < 40) {
      return '#22c55e'; // green-500
    } else if (durationMinutes < 60) {
      return '#f97316'; // orange-500
    } else {
      return '#ef4444'; // red-500
    }
  }, [transitTimes]);

  const pointToLayerRailwayStation = useCallback((feature, latlng) => {
    // Square marker. Using rectangle relative to center point to scale with map.
    // Radius ~150m effectively means a square with side ~300m
    const radiusMeters = 150;

    // Approximation for meters to degrees
    const latOffset = radiusMeters / 111320;
    const lngOffset = radiusMeters / (111320 * Math.cos(latlng.lat * (Math.PI / 180)));

    const bounds = [
      [latlng.lat - latOffset, latlng.lng - lngOffset],
      [latlng.lat + latOffset, latlng.lng + lngOffset]
    ];

    const color = getStationColor(feature.properties.name);

    return L.rectangle(bounds, {
      stroke: false,
      color: color,
      fillColor: color,
      fillOpacity: 1,
      pane: 'school-sites-pane'
    });
  }, [getStationColor]);

  const onEachRailwayStation = useCallback((feature, layer) => {
    if (feature.properties && feature.properties.name) {
      const stationName = feature.properties.name;
      const transit = transitTimes ? transitTimes[stationName] : null;

      let tooltipContent = `<strong>${stationName}</strong>`;
      if (transit) {
        tooltipContent += `<br/><span style="font-size: 0.85em;">→ Central: ${transit.durationText}</span>`;
      }

      layer.bindTooltip(tooltipContent, {
        permanent: false,
        direction: 'top',
        className: 'station-label',
        offset: [0, -10]
      });
    }
  }, [transitTimes]);


  return (
    <MapContainer
      center={[-27.47, 153.02]}
      zoom={11}
      style={{ height: '100%', width: '100%' }}
      className="z-0"
    >
      <ZoomHandler />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Pane name="school-sites-pane" style={{ zIndex: 650 }} />
      {showCatchments && geoData && (
        <GeoJSON
          data={geoData}
          style={style}
          onEachFeature={onEachFeature}
        />
      )}
      {showSchoolLocations && schoolSites && (
        <GeoJSON
          data={schoolSites}
          pointToLayer={pointToLayerSchoolSite}
          onEachFeature={onEachSchoolSite}
        />
      )}
      {showRailwayStations && railwayStations && (
        <GeoJSON
          key={transitTimes ? 'stations-with-times' : 'stations-loading'}
          data={railwayStations}
          pointToLayer={pointToLayerRailwayStation}
          onEachFeature={onEachRailwayStation}
        />
      )}
    </MapContainer>
  );
};

export default MapComponent;

