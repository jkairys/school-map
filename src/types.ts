export interface School {
  id: string;
  name: string;
  type: 'State' | 'Catholic' | 'Independent';
  level: 'Primary' | 'Secondary' | 'Combined';
  address: string;
  suburb: string;
  postcode: string;
  latitude: number;
  longitude: number;
  icsea?: number; // Index of Community Socio-Educational Advantage
  naplanReading?: number;
  naplanWriting?: number;
  naplanNumeracy?: number;
  naplanAverage?: number;
  enrollment?: number;
  website?: string;
  catchmentBoundary?: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}

export interface FilterState {
  schoolType: string[];
  minICSEA?: number;
  maxICSEA?: number;
  searchQuery: string;
  showCatchments: boolean;
}

export interface CatchmentFeature {
  type: 'Feature';
  properties: {
    name: string;
    description?: string | { '@type': string; value: string };
    [key: string]: unknown;
  };
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}

export interface CatchmentData {
  type: 'FeatureCollection';
  metadata: {
    source: string;
    description: string;
    license: string;
    downloadedAt: string;
    originalUrl: string;
  };
  features: CatchmentFeature[];
}
