// Plain hex color palette for Earth-observation hazard-focus categories —
// deliberately has zero dependencies (no Cesium) so importing it doesn't
// pull the ~cesium bundle into whichever chunk needs the palette. EoGlobe.jsx
// derives its Cesium.Color objects from this; EoSkyPlot.jsx, EoLocationPicker.jsx
// and EarthObservation.jsx use these plain strings directly for CSS/SVG.
export const CATEGORY_COLOR = {
  'Fire Detection': '#ff8a5c',
  'Storm & Weather Tracking': '#ffd166',
  'Flood & Precipitation Monitoring': '#5ec8ff',
  'General Earth Observation': '#8fe3c7',
}

export const CATEGORY_ORDER = [
  'Fire Detection',
  'Storm & Weather Tracking',
  'Flood & Precipitation Monitoring',
  'General Earth Observation',
]
