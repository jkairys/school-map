import React, { useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet';
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

const MapComponent = ({ onSchoolHover, selectedCompetency }) => {
  const [geoData, setGeoData] = useState(null);
  const [schoolData, setSchoolData] = useState(null);
  const [stateAverages, setStateAverages] = useState(null);

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
          color: '#333',
          dashArray: '',
          fillOpacity: 0.9
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
          dashArray: '3',
          fillOpacity: 0.6
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
      dashArray: '3',
      fillOpacity: 0.6
    };
  }, [schoolData, stateAverages, selectedCompetency]);

  return (
    <MapContainer
      center={[-27.47, 153.02]}
      zoom={11}
      style={{ height: '100%', width: '100%' }}
      className="z-0"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {geoData && (
        <GeoJSON
          data={geoData}
          style={style}
          onEachFeature={onEachFeature}
        />
      )}
    </MapContainer>
  );
};

export default MapComponent;
