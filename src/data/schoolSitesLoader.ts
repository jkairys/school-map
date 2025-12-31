import schoolSitesRaw from './schoolSites.json';

export interface SchoolSite {
  name: string;
  code: string | null;
  latitude: number;
  longitude: number;
}

interface SchoolSitesData {
  metadata: {
    source: string;
    description: string;
    license: string;
    downloadedAt: string;
    originalUrl: string;
  };
  schools: Array<{
    name: string;
    code: string | null;
    latitude: number;
    longitude: number;
    rawProperties: unknown;
  }>;
}

const schoolSitesData = schoolSitesRaw as SchoolSitesData;

export const schoolSites: SchoolSite[] = schoolSitesData.schools.map(s => ({
  name: s.name,
  code: s.code,
  latitude: s.latitude,
  longitude: s.longitude
}));

export const schoolSitesMetadata = schoolSitesData.metadata;

// Helper to find a school site by name
export function findSchoolSiteByName(name: string): SchoolSite | undefined {
  const normalizedSearch = name.toLowerCase().trim();
  return schoolSites.find(s => {
    const siteName = s.name.toLowerCase().trim();
    return siteName === normalizedSearch ||
           siteName.includes(normalizedSearch) ||
           normalizedSearch.includes(siteName);
  });
}
