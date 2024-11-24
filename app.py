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
from dash_extensions.javascript import assign, arrow_function
import geopandas as gpd

# from geopy.geocoders import Nominatim
import warnings
import requests

http_user_agent = r"food-desert-analysis.com/1.0 (jfarina3@gatech.edu)"
http_referrer = "food-desert-analysis.com"
ox.settings.http_user_agent = http_user_agent
ox.settings.http_referrer = http_referrer
headers = {
    "User-Agent": http_user_agent,
    "Referer": http_referrer,
}

requests.utils.default_headers().update(headers)

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
def create_geo_json_data(location_state, gdf=False):
    filename = f"geo_json_{location_state.lower()}.json"
    primary_path = os.path.join("data", filename)
    fallback_path = os.path.join("src", "data", filename)
    for file_path in [primary_path, fallback_path]:
        try:
            if gdf:
                return gpd.from_file(file_path)
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
    response = requests.get(url, headers=headers)
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
    if svi.startswith("E_"):
        properties_max = max(properties_values)
    elif svi.startswith("EPL_") or svi.startswith("RPL_") or svi.startswith("EP_"):
        properties_max = 1.0
    properties_min = 0  # min(properties_values)
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

    classes = np.linspace(
        properties_min, properties_max * 1.001, len(colorscale) + 1
    ).tolist()

    style = dict(weight=2, opacity=0.2, color="white", dashArray="3", fillOpacity=0.7)

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
        if (value == null) {
            style.fillColor= '#808080';  
            return style;
        }
        for (let i = 0; i < classes.length; i++) {
            if (value >= classes[i] && value < classes[i+1]) {
                style.fillColor = colorscale[i];  // set the fill color according to the class
                break;
            }
        }
        return style;
    }"""
    )

    return style_handle, colorscale, classes, style, colorbar


# create tooltip
def get_info(feature=None, svi_variable="E_TOTPOP"):
    # header = [html.B("SVI Hover Display", style={"fontSize":"14px"}), html.Br()]
    if not feature or svi_variable == "None":
        return [html.B(svi_variable, style={"fontSize": "14px"}), html.Br(), "--"]
    return [
        html.B(svi_variable, style={"fontSize": "14px"}),
        html.Br(),
        feature["properties"][svi_variable],
    ]


info = html.Div(
    children=get_info(),
    id="info_tooltip",
    className="info_tooltip",
    style={
        "position": "absolute",
        "top": "575px",
        "right": "23px",
        "zIndex": 500,
        "backgroundColor": "rgba(255, 255, 255, 0.7)",
        "padding": "5px",
        "border": "1px solid #ccc",
        "borderRadius": "5px",
    },
)


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
                    url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                ),
                name="tile-pane",
                style={"zIndex": 10},
            ),
            # Choropleth layer
            dl.Pane(
                dl.LayerGroup(id="choropleth-layer"),
                name="choropleth-pane",
                style={"zIndex": 20},
            ),
            # Search area highlight
            dl.Pane(
                dl.LayerGroup(id="boundary-layer"),
                name="boundary-pane",
                style={"zIndex": 25},
            ),
            dl.Pane(
                dl.TileLayer(
                    url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png",
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                ),
                name="tile-labels-pane",
                style={"zIndex": 35},
            ),
            # POI layers
            dl.Pane(
                name="store-layers",
                children=dl.LayersControl(
                    [
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="grocery-layer"),
                                name="grocery-pane",
                                style={"zIndex": 60},
                            ),
                            name="Grocery Stores",
                            checked=True,
                        ),
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="convenience-layer"),
                                name="convenience-pane",
                                style={"zIndex": 50},
                            ),
                            name="Convenience Stores",
                            checked=True,
                        ),
                        dl.Overlay(
                            dl.Pane(
                                dl.LayerGroup(id="lowquality-layer"),
                                name="lowquality-pane",
                                style={"zIndex": 40},
                            ),
                            name="Low Quality (Fast Food)",
                            checked=True,
                        ),
                    ]
                ),
                style={"zIndex": 500},
            ),
            # Colorbar (overlay)
            dl.Pane(
                html.Div(id="colorbar-container"),
                name="colorbar-pane",
                style={"zIndex": 500},
            ),
            # Legend
            html.Div(
                id="legend",
                style={
                    "position": "absolute",
                    "bottom": "20px",
                    "right": "10px",
                    "zIndex": 500,
                    "backgroundColor": "rgba(255, 255, 255, 0.7)",
                    "padding": "5px",
                    "border": "1px solid #ccc",
                    "borderRadius": "5px",
                },
                children=[
                    html.H5(
                        "Legend", style={"marginBottom": "10px", "fontSize": "14px"}
                    ),
                    html.Div(
                        style={
                            "display": "flex",
                            "flexDirection": "column",
                            "alignItems": "flex-center",
                            "gap": "5px",
                        },
                        children=[
                            html.Div(
                                style={
                                    "display": "flex",
                                    "alignItems": "flex-center",
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "width": "20px",
                                            "height": "20px",
                                            "backgroundColor": "#4daf4a",
                                            "borderRadius": "50%",
                                            "marginRight": "5px",
                                        }
                                    ),
                                    html.Span("Grocery Stores"),
                                ],
                            ),
                            html.Div(
                                style={
                                    "display": "flex",
                                    "alignItems": "flex-center",
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "width": "15px",
                                            "height": "15px",
                                            "backgroundColor": "#377eb8",
                                            "borderRadius": "50%",
                                            "marginRight": "8px",
                                            "marginLeft": "2px",
                                            "marginTop": "2px",
                                        }
                                    ),
                                    html.Span("Convenience Stores"),
                                ],
                            ),
                            html.Div(
                                style={
                                    "display": "flex",
                                    "alignItems": "flex-center",
                                },
                                children=[
                                    html.Div(
                                        style={
                                            "width": "10px",
                                            "height": "10px",
                                            "backgroundColor": "#e41a1c",
                                            "borderRadius": "50%",
                                            "marginRight": "11px",
                                            "marginLeft": "4px",
                                            "marginTop": "3px",
                                        }
                                    ),
                                    html.Span("Low Quality (Fast Food)"),
                                ],
                            ),
                        ],
                    ),
                ],
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
    geo_json_data = json.loads(gdf.geometry.boundary.to_json())

    boundary_style = {
        "weight": 2,
        "opacity": 1,
        "color": "black",
        "fillOpacity": 0,
        "dashArray": "5",
        "pointer-events": "none",
    }

    boundary = dl.GeoJSON(
        data=geo_json_data,
        style=boundary_style,
        interactive=False,
        hoverStyle={"weight": 5, "color": "#666"},
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
    try:
        grocery = groceries_from_placename(placename, centroids_only=True)
        convenience = convenience_from_placename(placename, centroids_only=True)
        lowquality = lowquality_from_placename(placename, centroids_only=True)
    except ox._errors.InsufficientResponseError as e:
        print(e)
        return dash.no_update, dash.no_update, dash.no_update

    return (
        poi_to_markers(grocery, color="#4daf4a", radius=10),
        poi_to_markers(convenience, color="#377eb8", radius=6),
        poi_to_markers(lowquality, color="#e41a1c", radius=3),
    )


@app.callback(
    Output("choropleth-layer", "children"),
    Output("colorbar-container", "children"),
    Input("location-input", "n_submit"),
    Input("SVI-val-dropdown", "value"),
    Input("failed-search", "is_open"),
    Input("map", "viewport"),
    State("location-input", "value"),
)
def update_choropleth(n_submit, svi_variable, failed_search, viewport, _):
    if failed_search:
        return dash.no_update, dash.no_update

    if svi_variable == "None":
        return [], []

    # SVI update is now triggered by change in viewport
    bounds = np.array(viewport["bounds"])
    center = bounds.mean(axis=0)

    # Get center and state
    location_state = find_state(center)

    # Create choropleth
    geo_json_data = create_geo_json_data(location_state)

    style_handle, colorscale, classes, style, colorbar = generate_style_handle(
        svi_variable, geo_json_data
    )
    # mapping geojson to styler to fills in the choropleth
    choropleth = dl.GeoJSON(
        data=geo_json_data,
        style=style_handle,
        zoomToBoundsOnClick=False,
        hoverStyle=arrow_function({"weight": 5, "color": "#666", "dashArray": ""}),
        hideout=dict(
            colorscale=colorscale,
            classes=classes,
            style=style,
            colorProp=svi_variable,
        ),
        id="choropleth-layer",
    )

    return choropleth, colorbar


modal = html.Div(
    [
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle("Welcome!"), class_name="bg-dark text-light"
                ),
                dbc.ModalBody(
                    [
                        html.P(
                            [
                                html.Br(),
                                "This is a visual representation of food access across the United States. ",
                                html.Br(),
                                "We hope you can find interesting patterns of how food access and social indicators are related in your city",
                                html.Br(),
                            ]
                        ),
                        html.P(
                            [
                                html.B("What are SVI Variables?"),
                                html.Br(),
                                "The Center for Disease Control developed the Social Vulnerability Index (SVI) to better understand where disadvantaged populations live. There are many different SVI's measured by the CDC and we have provided a sample of them including:",
                                html.Br(),
                                html.Ul(
                                    [
                                        html.Li(
                                            "E_TOTPOP: A simple count of the total population of a census tract"
                                        ),
                                        html.Li(
                                            "E_POV150: The count of people in an area living below 150% of the poverty line"
                                        ),
                                        html.Li(
                                            "E_UNINSR: The count of people in an area without health insurance"
                                        ),
                                        html.Li(
                                            "E_LIMENG: The count of people in an area who speak English 'less than well'"
                                        ),
                                        html.Li(
                                            "E_MINRTY: The count of people in an area who are non-white and non-Hispanic"
                                        ),
                                        html.Li(
                                            "E_MOBILE: The count of people in an area who are living in mobile homes"
                                        ),
                                        html.Li(
                                            "E_NOVEH: The count of people in an area without ownership of a vehicle"
                                        ),
                                        html.Li(
                                            "EPL_POV150: The national percentile of people in an area living below 150% of the poverty line"
                                        ),
                                        html.Li(
                                            "RPL_THEMES: This is an overall summary of all of the SVI's"
                                        ),
                                    ],
                                    style={
                                        "marginTop": "0.5rem",
                                        "marginBottom": "0.5rem",
                                        "paddingLeft": "2rem",
                                    },
                                ),
                                "In general, higher SVI scores mean more socially vulnerable people live in an area.",
                                html.Br(),
                                "If you would like to learn more about the SVI variables, please refer to ",
                                html.A(
                                    "this CDC link.",
                                    href="https://svi.cdc.gov/map/data/docs/SVI2022Documentation_5.17.2024.pdf",
                                    target="_blank",
                                ),
                            ]
                        ),
                    ],
                    class_name="bg-dark  text-light",
                ),
                dbc.ModalFooter(
                    dbc.Button("Close", id="close", className="ms-auto", n_clicks=0),
                    class_name="bg-dark  text-light",
                ),
            ],
            id="modal",
            scrollable=True,
            size="lg",
            centered=True,
            is_open=True,
        ),
    ]
)


# App layout with dropdown to select location and map
app.layout = dbc.Container(
    [
        modal,
        dbc.Row(dbc.Col(html.H1("Food Access Explorer", className="text-center mb-4"))),
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
                                html.Label(
                                    "Select a Location:",
                                    className="mb-2",
                                    htmlFor="location-input",
                                ),
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
                                            "label": "Total Population (E_TOTPOP)",
                                            "value": "E_TOTPOP",
                                        },
                                        {
                                            "label": "Population Below 150% of Poverty Level (E_POV150)",
                                            "value": "E_POV150",
                                        },
                                        {
                                            "label": "No Health Insurance (E_UNINSUR)",
                                            "value": "E_UNINSUR",
                                        },
                                        {
                                            "label": "English Language Proficiency (E_LIMENG)",
                                            "value": "E_LIMENG",
                                        },
                                        {
                                            "label": "Racial & Ethnic Minority (E_MINRTY)",
                                            "value": "E_MINRTY",
                                        },
                                        {
                                            "label": "Mobile Homes (E_MOBILE)",
                                            "value": "E_MOBILE",
                                        },
                                        {
                                            "label": "No Vehicles (E_NOVEH)",
                                            "value": "E_NOVEH",
                                        },
                                        {
                                            "label": "National Percentile Persons Below 150% Poverty (EPL_POV150)",
                                            "value": "EPL_POV150",
                                        },
                                        {
                                            "label": "Percentile Ranking for Socioeconomic Status Theme (RPL_THEME1)",
                                            "value": "RPL_THEME1",
                                        },
                                        {
                                            "label": "Overall Percentile Ranking (RPL_THEMES)",
                                            "value": "RPL_THEMES",
                                        },
                                        {
                                            "label": "None - No Selection",
                                            "value": "None",
                                        },
                                    ],
                                    value="E_TOTPOP",
                                    className="mb-4",
                                    style=dict(
                                        width="100%", position="relative", zIndex=1000
                                    ),
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
        dbc.Row(dbc.Col(html.Div(id="map-container", children=[init_map(), info]))),
    ],
    fluid=True,
    
)


@app.callback(
    Output("info_tooltip", "children"),
    Input("choropleth-layer", "hoverData"),
    Input("SVI-val-dropdown", "value"),
    prevent_initial_callbacks=True,
)
def info_hover(feature, svi_variable):
    return get_info(feature, svi_variable)


@app.callback(
    Output("modal", "is_open"),
    Input("close", "n_clicks"),
    [State("modal", "is_open")],
)
def toggle_modal(n1, is_open):
    if n1:
        return not is_open
    return is_open


# Run the app
if __name__ == "__main__":
    app.run_server(debug=False)
