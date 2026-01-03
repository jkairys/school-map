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

import { calculateStateAverages, getSchoolRelativeScore } from '../utils/naplanUtils';

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



const MapComponent = ({ onSchoolHover, selectedCompetency, showCatchments, showSchoolLocations, showRailwayStations }) => {
  const [geoData, setGeoData] = useState(null);
  const [schoolData, setSchoolData] = useState(null);
  const [stateAverages, setStateAverages] = useState(null);
  const [schoolSites, setSchoolSites] = useState(null);
  const [railwayStations, setRailwayStations] = useState(null);
  const [transitTimes, setTransitTimes] = useState(null);

  useEffect(() => {
    // Load Catchments
    fetch('/data/catchments.geojson')
      .then(res => res.json())
      .then(data => setGeoData(data))
      .catch(err => console.error("Error loading GeoJSON:", err));

    // Load NAPLAN Data
    fetch('/data/naplan_data.json')
      .then(res => res.json())
      .then(data => {
        setSchoolData(data);
        const averages = calculateStateAverages(data);
        setStateAverages(averages);
      })
      .catch(err => console.error("Error loading NAPLAN data:", err));

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

  const getSchoolColor = (name) => {
    if (!schoolData || !schoolData[name] || !stateAverages || !selectedCompetency) {
      // Fallback or No Data
      return '#d1d5db'; // Gray 300
    }

    const school = schoolData[name];
    const score = getSchoolRelativeScore(school, selectedCompetency, stateAverages);

    if (score === null) return '#d1d5db';

    // Thresholds
    // < 0.95: Red
    // 0.95 - 1.0: Orange  (User: "orange for a little bit under average")
    // 1.0 - 1.05: Light Green
    // > 1.05: Dark Green

    if (score < 0.95) return '#ef4444'; // Red 500
    if (score < 1.0) return '#f97316'; // Orange 500
    if (score < 1.05) return '#86efac'; // Green 300
    return '#15803d'; // Green 700
  };

  const onEachFeature = useCallback((feature, layer) => {
    const { name, locality } = feature.properties;

    // Calculate score for tooltip
    let scoreText = 'No Data';
    let rawScore = null;

    if (schoolData && schoolData[name] && stateAverages && selectedCompetency) {
      const relScore = getSchoolRelativeScore(schoolData[name], selectedCompetency, stateAverages);
      if (relScore !== null) {
        rawScore = relScore.toFixed(2);
        scoreText = `${rawScore}x State Avg`;
      }
    }

    layer.bindTooltip(`
      <div class="text-sm font-sans">
        <strong class="block text-base">${name}</strong>
        <span class="text-gray-600">${locality || 'QLD'}</span>
        <div class="mt-1 font-mono text-xs text-gray-800">
           ${selectedCompetency}: <strong>${scoreText}</strong>
        </div>
      </div>
    `, { sticky: true });

    layer.on({
      mouseover: (e) => {
        const layer = e.target;
        layer.setStyle({
          weight: 3,
          color: 'white', // Keep white, just thicker
          dashArray: '',
          fillOpacity: 0.8
        });
        layer.bringToFront();

        // Pass data to parent
        if (onSchoolHover) {
          const data = schoolData ? schoolData[name] : null;
          onSchoolHover(data || { name });
        }
      },
      mouseout: (e) => {
        const layer = e.target;
        // Re-apply style
        layer.setStyle({
          fillColor: getSchoolColor(name),
          weight: 1,
          opacity: 1,
          color: 'white',
          dashArray: '', // Solid line now
          fillOpacity: 0.5
        });

        if (onSchoolHover) {
          onSchoolHover(null);
        }
      }
    });
  }, [schoolData, stateAverages, selectedCompetency, onSchoolHover]);

  const style = useCallback((feature) => {
    return {
      fillColor: getSchoolColor(feature.properties.name),
      weight: 1,
      opacity: 1,
      color: 'white',
      dashArray: '', // Solid line
      fillOpacity: 0.5
    };
  }, [schoolData, stateAverages, selectedCompetency]);

  const onEachSchoolSite = useCallback((feature, layer) => {
    // Label with school name
    if (feature.properties && feature.properties.name) {
      layer.bindTooltip(feature.properties.name, {
        permanent: true,
        direction: 'right',
        className: 'school-site-label',
        offset: [0, 0], // Center it better relative to the larger dot
        pane: 'school-sites-pane' // Ensure labels are also on top
      });
    }
  }, []);

  const pointToLayerSchoolSite = useCallback((feature, latlng) => {
    // Blue dot, no border. Using Circle (meters) so it scales with map.
    // Radius: 150 meters (approx size of a school) to be visible at lower zooms
    return L.circle(latlng, {
      radius: 150,
      stroke: false,
      color: '#2563eb', // blue-600
      fillColor: '#2563eb',
      fillOpacity: 1,
      pane: 'school-sites-pane' // Custom pane for Z-index
    });
  }, []);

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
    // 1 deg lat = 111,320 meters
    // 1 deg lng = 111,320 * cos(lat) meters

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
      pane: 'school-sites-pane' // Use same pane as schools for now, or create new one
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

