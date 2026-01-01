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

const MapComponent = ({ onSchoolHover }) => {
  const [geoData, setGeoData] = useState(null);
  const [schoolData, setSchoolData] = useState(null);

  useEffect(() => {
    // Load Catchments
    fetch('/data/catchments.geojson')
      .then(res => res.json())
      .then(data => setGeoData(data))
      .catch(err => console.error("Error loading GeoJSON:", err));

    // Load NAPLAN Data
    fetch('/data/naplan_data.json')
      .then(res => res.json())
      .then(data => setSchoolData(data))
      .catch(err => console.error("Error loading NAPLAN data:", err));
  }, []);

  // Hash function to generate color from string
  const getColorFromName = (name) => {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    // Generate HSL: Hue = hash % 360, Saturation = 70%, Lightness = 60%
    const hue = Math.abs(hash % 360);
    return `hsl(${hue}, 70%, 60%)`;
  };

  const onEachFeature = useCallback((feature, layer) => {
    const { name, locality } = feature.properties;
    layer.bindTooltip(`
      <div class="text-sm font-sans">
        <strong class="block text-base">${name}</strong>
        <span class="text-gray-600">${locality || 'QLD'}</span>
      </div>
    `, { sticky: true });

    layer.on({
      mouseover: (e) => {
        const layer = e.target;
        layer.setStyle({
          weight: 3,
          color: '#333',
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
        // Reset style is handled by GeoJSON component usually passing style prop again?? 
        // Actually Leaflet's resetStyle requires reference to the GeoJSON layer group which we don't easily have here.
        // But if we simply re-apply the feature style manually using the same function:
        const layer = e.target;
        layer.setStyle({
          fillColor: getColorFromName(name),
          weight: 1,
          opacity: 1,
          color: 'white',
          dashArray: '3',
          fillOpacity: 0.35
        });

        if (onSchoolHover) {
          onSchoolHover(null);
        }
      }
    });
  }, [schoolData, onSchoolHover]); // Re-create if schoolData changes

  const style = useCallback((feature) => {
    return {
      fillColor: getColorFromName(feature.properties.name),
      weight: 1,
      opacity: 1,
      color: 'white',
      dashArray: '3',
      fillOpacity: 0.35
    };
  }, []); // Empty deps = stable style function

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
