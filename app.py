import os
import sys
import numpy as np
import dash
import dash_leaflet as dl
import dash_leaflet.express as dlx
import osmnx as ox
from dash import html, dcc
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import json
from dash_extensions.javascript import assign

# from geopy.geocoders import Nominatim
import warnings
import requests


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


first_time = True
DEFAULT_PLACENAME = "Denver, CO"
DEFAULT_SVI_VARIABLE = "E_POV150"
LEAFLET_CRS = 3857
# Dash app setup
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server


def clean_invalid_values(geojson, invalid_value=-999):
    for record in geojson["features"]:
        for key in record["properties"].keys():
            if record["properties"][key] == -999:
                record["properties"][key] = np.nan
    return geojson


# Load GeoJSON data from file
def create_geo_json_data(location_state):
    filename = f"geo_json_{location_state.lower()}.json"
    primary_path = os.path.join("data", filename)
    fallback_path = os.path.join("src", "data", filename)
    for file_path in [primary_path, fallback_path]:
        try:
            with open(file_path) as f:
                geojson_data = json.load(f)
                # Clean invalid values after loading
                return clean_invalid_values(geojson_data)
        except FileNotFoundError:
            continue

    # If we get here, neither path worked
    raise FileNotFoundError(
        f"Could not find GeoJSON file for state {location_state} "
        f"in either {primary_path} or {fallback_path}"
    )


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


# def get_map_components(
#     grocery_markers, convenience_markers, lowquality_markers, svi, geo_json_data
# ):

#     return_value = [
#         dl.TileLayer(
#             url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
#             attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
#             maxZoom=20,
#         ),
#     ]

#     if svi != "None":
#         style_handle, colorscale, classes, style, colorbar = generate_style_handle(
#             svi, geo_json_data
#         )
#         return_value.append(
#             dl.Pane(
#                 dl.GeoJSON(
#                     data=geo_json_data,
#                     id="geojson-layer",
#                     style=style_handle,  # apply style from JavaScript
#                     # zoomToBounds=True,  # when true, zooms to bounds when data changes (e.g. on load)
#                     # zoomToBoundsOnClick=True,  # when true, zooms to bounds of feature (e.g. polygon) on click
#                     hoverStyle={"weight": 5, "color": "#666", "dashArray": ""},
#                     hideout=dict(
#                         colorscale=colorscale,
#                         classes=classes,
#                         style=style,
#                         colorProp=svi,
#                     ),
#                 ),
#                 name="middle",
#             )
#         )

#         return_value.append(colorbar)

#     return_value.append(
#         dl.Pane(
#             dl.LayersControl(
#                 [
#                     dl.Overlay(
#                         dl.LayerGroup(grocery_markers), name="Groceries", checked=True
#                     ),
#                     dl.Overlay(
#                         dl.LayerGroup(convenience_markers),
#                         name="Convenience (General Stores, and Convenience Stores)",
#                         checked=True,
#                     ),
#                     dl.Overlay(
#                         dl.LayerGroup(lowquality_markers),
#                         name="Low-quality (Fast-Food and Gas Stations)",
#                         checked=True,
#                     ),
#                 ]
#             ),
#             name="upper",
#         )
#     )

#     return return_value


def init_map():
    return dl.Map(
        id="map",
        zoom=12,
        center=ox.geocode(DEFAULT_PLACENAME),
        style={"width": "100%", "height": "600px"},
        children=[
            # Base tile layer (bottom)
            dl.Pane(
                dl.TileLayer(
                    url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                ),
                name="tile-pane",
                style={"zIndex": 100},
            ),
            # Choropleth layer
            dl.Pane(
                dl.LayerGroup(id="choropleth-layer"),
                name="choropleth-pane",
                style={"zIndex": 200},
            ),
            # search area highlight
            dl.Pane(
                dl.LayerGroup(id="boundary-layer"),
                name="boundary-pane",
                style={"zIndex": 250},
            ),
            # layer control and poi layers
            dl.Pane(
                name="store-layers",
                children=dl.LayersControl(
                    [
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="grocery-layer"),
                                name="grocery-pane",
                                style={"zIndex": 600},
                            ),
                            name="grocery-overlay",
                            checked=True,
                        ),
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="convenience-layer"),
                                name="convenience-pane",
                                style={"zIndex": 500},
                            ),
                            name="convenience-overlay",
                            checked=True,
                        ),
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="lowquality-layer"),
                                name="lowquality-pane",
                                style={"zIndex": 400},
                            ),
                            name="lowquality-overlay",
                            checked=True,
                        ),
                    ]
                ),
                style={"zIndex": 9998},
            ),
            # Colorbar (overlay)
            dl.Pane(
                html.Div(id="colorbar-container"),
                name="colorbar-pane",
                style={"zIndex": 9999},
            ),
        ],
    )


@app.callback(
    Output("map", "viewport"),
    Output("boundary-layer", "children"),
    Output("failed-search", "is_open"),
    Output("failed-search", "children"),
    Input("location-input", "n_submit"),
    Input("SVI-val-dropdown", "value"),
    State("location-input", "value"),
)
def fly_to_place(n_submit, _, placename):
    if not n_submit:
        placename = DEFAULT_PLACENAME

    try:
        gdf = ox.geocode_to_gdf(placename)

    except Exception as e:
        print(f"Error geocoding {placename}: {e}")
        # Fallback to Denver coordinates if geocoding fails
        return (
            dash.no_update,
            dash.no_update,
            True,
            f"Location lookup unsuccessful: {e}",
        )

    bounds = gdf.total_bounds
    bounds = bounds[[1, 0, 3, 2]].reshape(2, 2).tolist()
    geo_json_data = json.loads(gdf.geometry.to_json())

    boundary_style = dict(
        weight=2, opacity=1, color="black", fillOpacity=0, dashArray="5"
    )

    boundary = dl.GeoJSON(
        data=geo_json_data,
        style=boundary_style,
        hoverStyle={"weight": 3, "color": "#666"},
    )

    return {"bounds": bounds}, boundary, False, ""


@app.callback(
    Output("grocery-layer", "children"),
    Output("convenience-layer", "children"),
    Output("lowquality-layer", "children"),
    Input("location-input", "n_submit"),
    Input("SVI-val-dropdown", "value"),
    Input("failed-search", "is_open"),
    State("location-input", "value"),
)
def update_map_markers(n_submit, _, failed_search, placename):
    # throwaway the svi value, but use the trigger
    if failed_search:
        return dash.no_update, dash.no_update, dash.no_update
    grocery = groceries_from_placename(placename, centroids_only=True)
    convenience = convenience_from_placename(placename, centroids_only=True)
    lowquality = lowquality_from_placename(placename, centroids_only=True)

    return (
        poi_to_markers(grocery, color="#4daf4a", radius=10),
        poi_to_markers(convenience, color="#377eb8", radius=7),
        poi_to_markers(lowquality, color="#e41a1c", radius=5),
    )


@app.callback(
    Output("choropleth-layer", "children"),
    Output("colorbar-container", "children"),
    Input("location-input", "n_submit"),
    Input("SVI-val-dropdown", "value"),
    Input("failed-search", "is_open"),
    State("location-input", "value"),
)
def update_choropleth(n_submit, svi_variable, failed_search, placename):
    if failed_search:
        return dash.no_update, dash.no_update
    if not n_submit:
        placename = DEFAULT_PLACENAME
    if svi_variable == "None":
        return [], []

    # Get center and state
    grocery = groceries_from_placename(placename, centroids_only=True)
    center = find_center_of_location(grocery)
    location_state = find_state(center)

    # Create choropleth
    geo_json_data = create_geo_json_data(location_state)
    style_handle, colorscale, classes, style, colorbar = generate_style_handle(
        svi_variable, geo_json_data
    )
    # mapping geojson to styler to fill in the choropleth
    choropleth = dl.GeoJSON(
        data=geo_json_data,
        style=style_handle,
        zoomToBoundsOnClick=True,
        hoverStyle={"weight": 5, "color": "#666", "dashArray": ""},
        hideout=dict(
            colorscale=colorscale,
            classes=classes,
            style=style,
            colorProp=svi_variable,
        ),
    )

    return choropleth, colorbar


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
                                            "label": "E_POV150 - Population Below 150% of Poverty Level",
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
        dbc.Row(
            dbc.Col(
                html.Div(
                    dbc.Alert(
                        "alert", id="failed-search", color="danger", is_open=False
                    )
                ),
                width=6,
            )
        ),
        dbc.Row(dbc.Col(html.Div(id="map-container", children=init_map()))),
        dbc.Row([
            dbc.Col(
                html.Div([
                dbc.Stack([
                    html.Div('Welcome. This is a visual representation of food access across the United States. '),
                    html.Div("If you enter a location in the left search bar, the map will search for food resources in the area selected."),
                    html.Div('The types of food resources searched are:'),
                    html.Div('- Grocery Stores - large green dots'),
                    html.Div('- Convenience Stores - mid-size blue dots'),
                    html.Div('- Fast Food - small red dots'),
                    html.Div("These food resource types can be toggled from the layer selector on the top right corner of the map"),
                    html.Div("When you enter a region, a dotted outline will show the boundary of the area.  This is the area that's being queried for food resources."),
                    ],
                    )
                ]),
            ),
            dbc.Col(
                html.Div([
                dbc.Stack([
                    html.Div("On the right hand side, CDC's Social Vulnerability Index (SVI) overlays can be selected."),
                    html.Div('Selecting one of these variables will create a heatmap of the census tracts in the area selected.'),
                    html.Div("\n"),
                    html.Div("We hope the tool proves useful for studying food accessibility.")
                ])
                ])
            )
        ]
        ),
    ],
    fluid=True,
 
)


# Run the app
if __name__ == "__main__":
    app.run_server(debug=False)
