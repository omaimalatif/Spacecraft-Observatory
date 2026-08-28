# NASA GIBS (Global Imagery Browse Services) — free, no API key, public tile
# server serving daily satellite imagery as standard WMTS/XYZ tiles.
# https://nasa-gibs.github.io/gibs-api-docs/
#
# Only layers verified against GIBS' own documented identifiers are listed
# here. Do not add a layer identifier without confirming it exists — GIBS
# will silently serve blank/black tiles for an unknown or mistyped layer
# name, which would look like "live data" while actually showing nothing.
#
# URL pattern (Web Mercator, matches Leaflet directly):
# https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{matrixSet}/{z}/{y}/{x}.{ext}

GIBS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"

LAYERS = [
    {
        "id": "modis-terra-truecolor",
        "category": "base",
        "label": "True Color (Terra/MODIS)",
        "layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "matrix_set": "GoogleMapsCompatible_Level9",
        "format": "jpg",
        "max_zoom": 9,
        "description": "Daily true-color imagery from the Terra satellite's MODIS instrument, 250m resolution.",
        "source": "NASA GIBS / MODIS Terra",
        "source_url": "https://www.earthdata.nasa.gov/gibs",
    },
    {
        "id": "modis-aqua-truecolor",
        "category": "base",
        "label": "True Color (Aqua/MODIS)",
        "layer": "MODIS_Aqua_CorrectedReflectance_TrueColor",
        "matrix_set": "GoogleMapsCompatible_Level9",
        "format": "jpg",
        "max_zoom": 9,
        "description": "Daily true-color imagery from the Aqua satellite's MODIS instrument, 250m resolution — a same-day second pass to compare against Terra.",
        "source": "NASA GIBS / MODIS Aqua",
        "source_url": "https://www.earthdata.nasa.gov/gibs",
    },
    {
        "id": "modis-terra-aerosol",
        "category": "atmosphere",
        "label": "Aerosol Optical Depth",
        "layer": "MODIS_Terra_Aerosol",
        "matrix_set": "GoogleMapsCompatible_Level6",
        "format": "png",
        "max_zoom": 6,
        "description": "Atmospheric aerosol concentration (dust, smoke, pollution) — unitless optical depth, higher values mean hazier skies.",
        "source": "NASA GIBS / MODIS Terra",
        "source_url": "https://www.earthdata.nasa.gov/gibs",
    },
]


def tile_url_template(layer: dict) -> str:
    return f"{GIBS_BASE}/{layer['layer']}/default/{{time}}/{layer['matrix_set']}/{{z}}/{{y}}/{{x}}.{layer['format']}"


def layers_payload() -> list[dict]:
    return [
        {**layer, "tile_url_template": tile_url_template(layer)}
        for layer in LAYERS
    ]
