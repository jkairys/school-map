import { School } from '../types'

// Sample data for Brisbane secondary schools
// Note: Catchment boundaries are simplified for demonstration
// Real data should be obtained from Queensland Department of Education

export const schools: School[] = [
  {
    id: 'brisbane-state-high',
    name: 'Brisbane State High School',
    type: 'State',
    level: 'Secondary',
    address: 'off Vulture St & Cordelia St',
    suburb: 'South Brisbane',
    postcode: '4101',
    latitude: -27.4758,
    longitude: 153.0179,
    icsea: 1132,
    naplanReading: 585,
    naplanWriting: 560,
    naplanNumeracy: 595,
    naplanAverage: 580,
    enrollment: 2400,
    website: 'https://brisbaneshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0050, -27.4650],
        [153.0250, -27.4650],
        [153.0250, -27.4850],
        [153.0050, -27.4850],
        [153.0050, -27.4650]
      ]]
    }
  },
  {
    id: 'kelvin-grove-state-college',
    name: 'Kelvin Grove State College',
    type: 'State',
    level: 'Combined',
    address: '60 Oakden St',
    suburb: 'Kelvin Grove',
    postcode: '4059',
    latitude: -27.4481,
    longitude: 153.0093,
    icsea: 1095,
    naplanReading: 560,
    naplanWriting: 545,
    naplanNumeracy: 570,
    naplanAverage: 558.3,
    enrollment: 2100,
    website: 'https://kelvingrovesc.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [152.9950, -27.4350],
        [153.0200, -27.4350],
        [153.0200, -27.4550],
        [152.9950, -27.4550],
        [152.9950, -27.4350]
      ]]
    }
  },
  {
    id: 'indooroopilly-state-high',
    name: 'Indooroopilly State High School',
    type: 'State',
    level: 'Secondary',
    address: 'Ward St',
    suburb: 'Indooroopilly',
    postcode: '4068',
    latitude: -27.5013,
    longitude: 152.9756,
    icsea: 1108,
    naplanReading: 570,
    naplanWriting: 552,
    naplanNumeracy: 580,
    naplanAverage: 567.3,
    enrollment: 1900,
    website: 'https://indooroopillyshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [152.9600, -27.4850],
        [152.9900, -27.4850],
        [152.9900, -27.5150],
        [152.9600, -27.5150],
        [152.9600, -27.4850]
      ]]
    }
  },
  {
    id: 'st-josephs-nudgee',
    name: "St Joseph's Nudgee College",
    type: 'Catholic',
    level: 'Secondary',
    address: '2199 Sandgate Rd',
    suburb: 'Boondall',
    postcode: '4034',
    latitude: -27.3453,
    longitude: 153.0621,
    icsea: 1125,
    naplanReading: 575,
    naplanWriting: 555,
    naplanNumeracy: 585,
    naplanAverage: 571.7,
    enrollment: 1600,
    website: 'https://www.nudgee.com',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0450, -27.3250],
        [153.0800, -27.3250],
        [153.0800, -27.3650],
        [153.0450, -27.3650],
        [153.0450, -27.3250]
      ]]
    }
  },
  {
    id: 'brisbane-grammar',
    name: 'Brisbane Grammar School',
    type: 'Independent',
    level: 'Secondary',
    address: 'Gregory Terrace',
    suburb: 'Spring Hill',
    postcode: '4000',
    latitude: -27.4594,
    longitude: 153.0278,
    icsea: 1158,
    naplanReading: 595,
    naplanWriting: 575,
    naplanNumeracy: 605,
    naplanAverage: 591.7,
    enrollment: 1700,
    website: 'https://www.brisbanegrammar.com',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0150, -27.4450],
        [153.0400, -27.4450],
        [153.0400, -27.4700],
        [153.0150, -27.4700],
        [153.0150, -27.4450]
      ]]
    }
  },
  {
    id: 'brisbane-girls-grammar',
    name: 'Brisbane Girls Grammar School',
    type: 'Independent',
    level: 'Secondary',
    address: '70 Gregory Terrace',
    suburb: 'Spring Hill',
    postcode: '4000',
    latitude: -27.4601,
    longitude: 153.0265,
    icsea: 1162,
    naplanReading: 598,
    naplanWriting: 580,
    naplanNumeracy: 600,
    naplanAverage: 592.7,
    enrollment: 1450,
    website: 'https://www.brisbanegirlsgrammar.com',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0150, -27.4450],
        [153.0400, -27.4450],
        [153.0400, -27.4700],
        [153.0150, -27.4700],
        [153.0150, -27.4450]
      ]]
    }
  },
  {
    id: 'cavendish-road-state-high',
    name: 'Cavendish Road State High School',
    type: 'State',
    level: 'Secondary',
    address: '931 Cavendish Rd',
    suburb: 'Holland Park',
    postcode: '4121',
    latitude: -27.5183,
    longitude: 153.0647,
    icsea: 1072,
    naplanReading: 550,
    naplanWriting: 535,
    naplanNumeracy: 560,
    naplanAverage: 548.3,
    enrollment: 1800,
    website: 'https://cavendishroadshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0450, -27.5000],
        [153.0850, -27.5000],
        [153.0850, -27.5350],
        [153.0450, -27.5350],
        [153.0450, -27.5000]
      ]]
    }
  },
  {
    id: 'churchie',
    name: 'Anglican Church Grammar School (Churchie)',
    type: 'Independent',
    level: 'Secondary',
    address: '45 Oaklands Parade',
    suburb: 'East Brisbane',
    postcode: '4169',
    latitude: -27.4825,
    longitude: 153.0467,
    icsea: 1145,
    naplanReading: 588,
    naplanWriting: 568,
    naplanNumeracy: 595,
    naplanAverage: 583.7,
    enrollment: 1550,
    website: 'https://www.churchie.qld.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0300, -27.4650],
        [153.0600, -27.4650],
        [153.0600, -27.5000],
        [153.0300, -27.5000],
        [153.0300, -27.4650]
      ]]
    }
  },
  {
    id: 'somerville-house',
    name: 'Somerville House',
    type: 'Independent',
    level: 'Secondary',
    address: '19 Graham St',
    suburb: 'South Brisbane',
    postcode: '4101',
    latitude: -27.4803,
    longitude: 153.0203,
    icsea: 1148,
    naplanReading: 590,
    naplanWriting: 570,
    naplanNumeracy: 592,
    naplanAverage: 584,
    enrollment: 1250,
    website: 'https://www.somerville.qld.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0050, -27.4700],
        [153.0350, -27.4700],
        [153.0350, -27.4900],
        [153.0050, -27.4900],
        [153.0050, -27.4700]
      ]]
    }
  },
  {
    id: 'clayfield-college',
    name: 'Clayfield College',
    type: 'Independent',
    level: 'Combined',
    address: '19 Gregory St',
    suburb: 'Clayfield',
    postcode: '4011',
    latitude: -27.4264,
    longitude: 153.0517,
    icsea: 1118,
    naplanReading: 572,
    naplanWriting: 558,
    naplanNumeracy: 578,
    naplanAverage: 569.3,
    enrollment: 1400,
    website: 'https://www.clayfieldcollege.qld.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0350, -27.4100],
        [153.0680, -27.4100],
        [153.0680, -27.4400],
        [153.0350, -27.4400],
        [153.0350, -27.4100]
      ]]
    }
  },
  {
    id: 'kenmore-state-high',
    name: 'Kenmore State High School',
    type: 'State',
    level: 'Secondary',
    address: 'Chelmer Rd',
    suburb: 'Kenmore',
    postcode: '4069',
    latitude: -27.5067,
    longitude: 152.9394,
    icsea: 1098,
    naplanReading: 562,
    naplanWriting: 548,
    naplanNumeracy: 572,
    naplanAverage: 560.7,
    enrollment: 2000,
    website: 'https://kenmoreshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [152.9200, -27.4900],
        [152.9600, -27.4900],
        [152.9600, -27.5250],
        [152.9200, -27.5250],
        [152.9200, -27.4900]
      ]]
    }
  },
  {
    id: 'mansfield-state-high',
    name: 'Mansfield State High School',
    type: 'State',
    level: 'Secondary',
    address: 'Ham Rd',
    suburb: 'Mansfield',
    postcode: '4122',
    latitude: -27.5358,
    longitude: 153.0997,
    icsea: 1105,
    naplanReading: 565,
    naplanWriting: 550,
    naplanNumeracy: 575,
    naplanAverage: 563.3,
    enrollment: 2200,
    website: 'https://mansfieldshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0800, -27.5200],
        [153.1200, -27.5200],
        [153.1200, -27.5550],
        [153.0800, -27.5550],
        [153.0800, -27.5200]
      ]]
    }
  },
  {
    id: 'sandgate-district-state-high',
    name: 'Sandgate District State High School',
    type: 'State',
    level: 'Secondary',
    address: 'Seymour St',
    suburb: 'Sandgate',
    postcode: '4017',
    latitude: -27.3212,
    longitude: 153.0697,
    icsea: 985,
    naplanReading: 525,
    naplanWriting: 510,
    naplanNumeracy: 535,
    naplanAverage: 523.3,
    enrollment: 1600,
    website: 'https://sandgatedistrictshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0500, -27.3050],
        [153.0900, -27.3050],
        [153.0900, -27.3400],
        [153.0500, -27.3400],
        [153.0500, -27.3050]
      ]]
    }
  },
  {
    id: 'aspley-state-high',
    name: 'Aspley State High School',
    type: 'State',
    level: 'Secondary',
    address: 'Graham Rd',
    suburb: 'Aspley',
    postcode: '4034',
    latitude: -27.3611,
    longitude: 153.0264,
    icsea: 978,
    naplanReading: 520,
    naplanWriting: 505,
    naplanNumeracy: 530,
    naplanAverage: 518.3,
    enrollment: 1750,
    website: 'https://aspleyshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [153.0050, -27.3450],
        [153.0450, -27.3450],
        [153.0450, -27.3800],
        [153.0050, -27.3800],
        [153.0050, -27.3450]
      ]]
    }
  },
  {
    id: 'mitchelton-state-high',
    name: 'Mitchelton State High School',
    type: 'State',
    level: 'Secondary',
    address: 'The Grange Rd',
    suburb: 'Mitchelton',
    postcode: '4053',
    latitude: -27.4161,
    longitude: 152.9792,
    icsea: 1015,
    naplanReading: 540,
    naplanWriting: 525,
    naplanNumeracy: 548,
    naplanAverage: 537.7,
    enrollment: 1850,
    website: 'https://mitcheltonshs.eq.edu.au',
    catchmentBoundary: {
      type: 'Polygon',
      coordinates: [[
        [152.9600, -27.4000],
        [152.9950, -27.4000],
        [152.9950, -27.4300],
        [152.9600, -27.4300],
        [152.9600, -27.4000]
      ]]
    }
  }
]
