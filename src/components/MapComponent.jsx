import React, { useEffect, useState } from 'react';
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

const MapComponent = () => {
  const [geoData, setGeoData] = useState(null);

  useEffect(() => {
    fetch('/data/catchments.geojson')
      .then(res => res.json())
      .then(data => setGeoData(data))
      .catch(err => console.error("Error loading GeoJSON:", err));
  }, []);

  const onEachFeature = (feature, layer) => {
    const { name, rank, locality } = feature.properties;
    layer.bindTooltip(`
      <div class="text-sm font-sans">
        <strong class="block text-base">${name}</strong>
        <span class="text-gray-600">${locality || 'QLD'}</span>
        ${rank ? `<div class="mt-1 font-bold ${getRankColor(rank)}">Rank: ${rank}/100</div>` : ''}
      </div>
    `, { sticky: true });

    layer.on({
      mouseover: (e) => {
        const layer = e.target;
        layer.setStyle({
          weight: 3,
          color: '#666',
          dashArray: '',
          fillOpacity: 0.7
        });
        layer.bringToFront();
      },
      mouseout: (e) => {
        const layer = e.target;
        // Reset style
        if (geoData) {
          // This is a simplified reset, ideally use geojson ref to resetStyle
          layer.setStyle(style(feature));
        }
      }
    });
  };

  const getRankColor = (rank) => {
    const r = parseInt(rank);
    if (!r) return 'text-gray-500';
    if (r >= 99) return 'text-green-600';
    if (r >= 95) return 'text-green-500';
    if (r >= 90) return 'text-lime-500';
    return 'text-yellow-500';
  };

  const style = (feature) => {
    const rank = parseInt(feature.properties.rank);
    let color = '#3388ff';
    let fillOpacity = 0.2;

    if (rank) {
      if (rank >= 99) color = '#15803d'; // green-700
      else if (rank >= 95) color = '#22c55e'; // green-500
      else if (rank >= 90) color = '#84cc16'; // lime-500
      else color = '#eab308'; // yellow-500
      fillOpacity = 0.4;
    }

    return {
      fillColor: color,
      weight: 1,
      opacity: 1,
      color: 'white',
      dashArray: '3',
      fillOpacity: fillOpacity
    };
  };

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
