import { CatchmentData, CatchmentFeature } from '../types';
import catchmentsRaw from './catchments.json';

// Type assertion for the imported JSON
const catchmentsData = catchmentsRaw as CatchmentData;

// Strip Z coordinate from coordinates (KML includes altitude as 0)
function stripZCoordinate(coords: number[][]): [number, number][] {
  return coords.map(coord => [coord[0], coord[1]] as [number, number]);
}

function processGeometry(geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon): GeoJSON.Polygon | GeoJSON.MultiPolygon {
  if (geometry.type === 'Polygon') {
    return {
      type: 'Polygon',
      coordinates: geometry.coordinates.map(ring => stripZCoordinate(ring as number[][]))
    };
  } else {
    return {
      type: 'MultiPolygon',
      coordinates: geometry.coordinates.map(polygon =>
        polygon.map(ring => stripZCoordinate(ring as number[][]))
      )
    };
  }
}

// Process all catchments with cleaned geometry
export const catchments: CatchmentFeature[] = catchmentsData.features.map(feature => ({
  ...feature,
  geometry: processGeometry(feature.geometry)
}));

// Export metadata
export const catchmentMetadata = catchmentsData.metadata;

// Helper to find catchment by school name
export function findCatchmentByName(schoolName: string): CatchmentFeature | undefined {
  const normalizedSearch = schoolName.toLowerCase()
    .replace(/state high school/g, 'shs')
    .replace(/state secondary college/g, 'state secondary college')
    .replace(/state college/g, 'state college')
    .replace(/high school/g, 'shs')
    .replace(/secondary college/g, 'secondary college')
    .trim();

  return catchments.find(c => {
    const catchmentName = c.properties.name.toLowerCase().trim();
    return catchmentName === normalizedSearch ||
           catchmentName.includes(normalizedSearch) ||
           normalizedSearch.includes(catchmentName);
  });
}

// Get all catchment names
export function getAllCatchmentNames(): string[] {
  return catchments.map(c => c.properties.name);
}
