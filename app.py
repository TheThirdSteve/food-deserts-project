import os
import sys
import numpy as np
import dash
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash import html, dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import json
from dash_extensions.javascript import assign
from geopy.geocoders import Nominatim
import warnings
import requests

first_time = True
# Adjust working directory and sys.path
current_dir = os.getcwd().split("/")[-1]
if current_dir in ("notebooks", "src"):
    os.chdir("..")
    parent_dir = os.path.abspath(os.getcwd())
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)


from src.poi_queries import (
    groceries_from_placename,
    convenience_from_placename,
    lowquality_from_placename,
)


def clean_invalid_values(geojson, invalid_value=-999):
    for record in geojson["features"]:
        for key in record["properties"].keys():
            if record["properties"][key] == -999:
                record["properties"][key] = np.nan
    return geojson


# Load GeoJSON data from file
def create_geo_json_data(location_state):
    geojson_path = f"src/data/geo_json_{location_state}.json".lower()
    geojson_data = {"type": "FeatureCollection", "features": []}

    geojson_data = clean_invalid_values(geojson=geojson_data)

    with open(geojson_path) as f:
        try:
            data = json.load(f)
        except FileNotFoundError as e:
            warnings.warn(f"{e}")
            data = json.load(rf"src/{f}")
        geojson_data["features"].extend(data["features"])

    return geojson_data


# Helper to convert POI GeoDataFrame to leaflet markers
def poi_to_markers(poi_gdf, color, radius):
    # print("POI Geometry:", poi_gdf["geometry"].head())  # Debugging
    markers = [
        dl.CircleMarker(
            center=[
                geom.y,
                geom.x,
            ],  # Extract latitude (y) and longitude (x) from the geometry
            color=color,
            radius=radius,
            fill=True,
            fillOpacity=0.5,
        )
        for geom in poi_gdf.geometry
    ]
    return markers


def find_center_of_location(grocery):
    coordinates = grocery.dissolve().to_crs("+proj=cea").centroid.to_crs(epsg=4326)
    center = [coordinates.y.values[0], coordinates.x.values[0]]
    return center


def find_state(center):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={center[0]}&lon={center[1]}&zoom=10&addressdetails=1"
    response = requests.get(url)
    data = response.json()
    address = data.get("address", {})
    state_code = address.get("ISO3166-2-lvl4", "").split("-")[-1]

    return state_code


def generate_style_handle(svi, geojson_data):

    if svi == "POP_DENSITY":
        e_totpop = [
            feature["properties"]["E_TOTPOP"] for feature in geojson_data["features"]
        ]
        area_sqmi = [
            feature["properties"]["AREA_SQMI"] for feature in geojson_data["features"]
        ]
        properties_values = [a / b for a, b in zip(e_totpop, area_sqmi)]
    else:
        properties_values = [
            feature["properties"][svi]
            for feature in geojson_data["features"]
            if feature["properties"][svi] != -999
        ]

    # properties_mean = sum(properties_values) / len(properties_values)
    properties_max = max(properties_values)
    properties_min = min(properties_values)

    # classes = [0, 10, 20, 50, 100, 200, 500, 1000]
    classes = np.linspace(properties_min, properties_max, 10).tolist()
    classes = [
        int(num) for num in np.linspace(properties_min, properties_max, 10).tolist()
    ]

    # classes = [properties_min + (properties_max - properties_min) * i / 9 for i in range(10)]
    colorscale = [
        "#FFEDA0",
        "#FED976",
        "#FEB24C",
        "#FD8D3C",
        "#FC4E2A",
        "#E31A1C",
        "#BD0026",
        "#800026",
    ]
    style = dict(weight=2, opacity=0.2, color="white", dashArray="3", fillOpacity=0.5)

    colorbar = dl.Colorbar(
        id="colorbar",
        classes=len(colorscale),
        colorscale=colorscale,
        width=400,
        height=10,
        opacity=0.7,
        min=properties_min,
        max=properties_max,
        position="bottomleft",
    )

    # JavaScript function to handle styling based on properties
    style_handle = assign(
        """function(feature, context){
        const {classes, colorscale, style, colorProp} = context.hideout;  // get props from hideout
        const value = feature.properties[colorProp];  // get value that determines the color
        for (let i = 0; i < classes.length; ++i) {
            if (value > classes[i]) {
                style.fillColor = colorscale[i];  // set the fill color according to the class
            }
        }
        return style;
    }"""
    )

    return style_handle, colorscale, classes, style, colorbar


def get_map_components(
    grocery_markers, convenience_markers, lowquality_markers, svi, geo_json_data
):

    return_value = [
        dl.TileLayer(
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            maxZoom=20,
        ),
    ]

    if svi != "None":
        style_handle, colorscale, classes, style, colorbar = generate_style_handle(
            svi, geo_json_data
        )
        return_value.append(
            dl.Pane(
                dl.GeoJSON(
                    data=geo_json_data,
                    id="geojson-layer",
                    style=style_handle,  # apply style from JavaScript
                    # zoomToBounds=True,  # when true, zooms to bounds when data changes (e.g. on load)
                    zoomToBoundsOnClick=True,  # when true, zooms to bounds of feature (e.g. polygon) on click
                    hoverStyle={"weight": 5, "color": "#666", "dashArray": ""},
                    hideout=dict(
                        colorscale=colorscale,
                        classes=classes,
                        style=style,
                        colorProp=svi,
                    ),
                ),
                name="middle",
            )
        )

        return_value.append(colorbar)

    return_value.append(
        dl.Pane(
            dl.LayersControl(
                [
                    dl.Overlay(
                        dl.LayerGroup(grocery_markers), name="Groceries", checked=True
                    ),
                    dl.Overlay(
                        dl.LayerGroup(convenience_markers),
                        name="Convenience",
                        checked=True,
                    ),
                    dl.Overlay(
                        dl.LayerGroup(lowquality_markers),
                        name="Low-quality",
                        checked=True,
                    ),
                ]
            ),
            name="upper",
        )
    )

    return return_value


# Function to generate a Dash Leaflet map with GeoJSON color scheme
def generate_map(location="Denver, CO", svi="E_POV150"):
    # Set map center based on selected location
    center = [39.7392, -104.9903]  # default to Denver, CO coordinates

    grocery = groceries_from_placename(location, centroids_only=True)
    convenience = convenience_from_placename(location, centroids_only=True)
    lowquality = lowquality_from_placename(location, centroids_only=True)

    if location != "Denver, CO":
        center = find_center_of_location(grocery)

    location_state = find_state(center)
    geo_json_data = create_geo_json_data(location_state)

    # Create marker layers
    grocery_markers = poi_to_markers(grocery, color="#4daf4a", radius=10)

    # grocery_markers = [
    # dl.Marker(position=(row.geometry.y, row.geometry.x), children=[
    #     dl.Popup(row.label)
    # ]) for idx, row in grocery.iterrows()]

    convenience_markers = poi_to_markers(convenience, color="#377eb8", radius=7)
    lowquality_markers = poi_to_markers(lowquality, color="#e41a1c", radius=5)

    # Create the map with POI markers and GeoJSON layer
    map_component = dl.Map(
        center=center,
        zoom=12,
        children=get_map_components(
            grocery_markers, convenience_markers, lowquality_markers, svi, geo_json_data
        ),
        style={"width": "100%", "height": "600px"},
    )

    return map_component


# Dash app setup
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# App layout with dropdown to select location and map
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H1("Grocery Stores and SVI Data", className="text-center mb-4")
            )
        ),
        dbc.Row(
            dbc.Col(
                html.Div(
                    style={
                        "display": "flex",
                        "justifyContent": "space-between",
                        "alignItems": "center",
                    },
                    children=[
                        html.Div(
                            style={"flex": "1", "marginRight": "10px"},
                            children=[
                                html.Label("Select a Location:", className="mb-2"),
                                dcc.Input(
                                    type="text",
                                    value="Denver, CO",
                                    id="location-input",
                                    className="mb-4",
                                    style=dict(width="100%"),
                                ),
                                # dcc.Dropdown(
                                #     id="location-dropdown",
                                #     options=[
                                #     {'label': 'Albany, NY', 'value': 'Albany, NY'},
                                #     {'label': 'New York, NY', 'value': 'New York, NY'},
                                #     {'label': 'Denver, CO', 'value': 'Denver, CO'},
                                #     {'label': 'Portland, ME', 'value': 'Portland, ME'},
                                #     ],
                                #     value="Denver, CO",
                                #     className="mb-4",
                                #     style=dict(width='100%')
                                # )
                            ],
                        ),
                        html.Div(
                            style={"flex": "1", "marginLeft": "10px"},
                            children=[
                                html.Label("Select an SVI Variable:", className="mb-2"),
                                dcc.Dropdown(
                                    id="SVI-val-dropdown",
                                    options=[
                                        {
                                            "label": "E_POV150 - Percentage of Population Below 150% of Poverty Level",
                                            "value": "E_POV150",
                                        },
                                        {
                                            "label": "E_TOTPOP - Total Population",
                                            "value": "E_TOTPOP",
                                        },
                                        {
                                            "label": "E_LIMENG - English Language Proficiency",
                                            "value": "E_LIMENG",
                                        },
                                        {
                                            "label": "AREA_SQMI - Area in Square Miles",
                                            "value": "AREA_SQMI",
                                        },
                                        {
                                            "label": "E_MOBILE - Mobile Homes",
                                            "value": "E_MOBILE",
                                        },
                                        {
                                            "label": "E_NOVEH - No Vehicles",
                                            "value": "E_NOVEH",
                                        },
                                        {
                                            "label": "None - No Selection",
                                            "value": "None",
                                        },
                                    ],
                                    value="E_TOTPOP",
                                    className="mb-4",
                                    style=dict(width="100%"),
                                ),
                            ],
                        ),
                    ],
                )
            )
        ),
        dbc.Row(dbc.Col(html.Div(id="map-container"))),
    ],
    fluid=True,
)


# Callback to update the map based on selected location
@app.callback(
    Output("map-container", "children"),
    Input("location-input", "n_submit"),
    State("location-input", "value"),
    Input("SVI-val-dropdown", "value"),
)
def update_map(n_submit, location, svi):
    if n_submit or location == "Denver, CO":
        return generate_map(location, svi)
    return dash.no_update


# Run the app
if __name__ == "__main__":
    app.run_server(debug=False)
