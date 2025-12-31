# Brisbane Schools Map

An interactive map showing secondary school catchments and rankings for Greater Brisbane, Queensland.

## Features

- Interactive map with school catchment boundaries
- Color-coded by ICSEA (Index of Community Socio-Educational Advantage) scores
- Filter by school type (State, Catholic, Independent)
- Search by school name or suburb
- Filter by ICSEA range
- Detailed school information including:
  - ICSEA scores
  - NAPLAN results
  - Enrollment numbers
  - School websites

## Getting Started

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

### Build

```bash
npm run build
```

## Data Sources

### Current Implementation

The current version uses sample data for demonstration purposes. The data includes:
- Real Brisbane secondary school locations
- Sample ICSEA scores based on typical ranges
- Simplified catchment boundaries for visualization

### Recommended Data Sources for Production

To create a production-ready version with accurate data, you should obtain data from:

1. **School Catchments**: Queensland Department of Education
   - Official catchment boundaries (GeoJSON format)
   - Available through Queensland Government Open Data Portal
   - URL: https://www.data.qld.gov.au/

2. **School Performance Data**:
   - ICSEA scores: Available from MySchool website (https://www.myschool.edu.au/)
   - NAPLAN results: Available from MySchool website
   - School profiles and enrollment data

3. **House Price Data** (Future Enhancement):
   - Domain.com.au API
   - CoreLogic API
   - Queensland Valuer-General

4. **Commute Time Data** (Future Enhancement):
   - Google Maps Distance Matrix API
   - HERE Maps API
   - Transport for Queensland data

## Roadmap

- [x] Phase 1: Basic map with school catchments and rankings
- [ ] Phase 2: Overlay house price data
- [ ] Phase 3: Add commute time calculations
- [ ] Phase 4: Add property search integration
- [ ] Phase 5: Add filters for specific destinations (e.g., CBD, universities)

## Technology Stack

- React 18
- TypeScript
- Vite
- Leaflet & React-Leaflet
- OpenStreetMap tiles

## License

MIT
