import os
import sys
import dash
import dash_leaflet as dl
from dash import html, dcc
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import json

from src.poi_queries import (
    groceries_from_placename,
    convenience_from_placename,
    lowquality_from_placename,
)

# Load GeoJSON data from file

current_dir = os.getcwd()
l = []
for filename in os.listdir(current_dir):
    filepath = os.path.join(current_dir, filename)
    l.append(filepath)

tex = "\n".join(l)

print("CURRREEEEENT DIR:", current_dir)
print(tex)

geojson_path = 'src/geo_json_test.json'
with open(geojson_path) as f:
    geojson_data = json.load(f)

# Helper to convert POI GeoDataFrame to leaflet markers
def poi_to_markers(poi_gdf, color, radius):
    print("POI Geometry:", poi_gdf["geometry"].head())  # Debugging
    markers = [
        dl.CircleMarker(
            center=[geom.y, geom.x],  # Extract latitude (y) and longitude (x) from the geometry
            color=color,
            radius=radius,
            fill=True,
            fillOpacity=0.5,
        )
        for geom in poi_gdf.geometry
    ]
    return markers

# Function to generate a Dash Leaflet map with POIs
def generate_map(location="Denver, CO"):
    grocery = groceries_from_placename(location, centroids_only=True)
    print("Grocery POIs:", grocery)  # Debugging

    convenience = convenience_from_placename(location, centroids_only=True)
    lowquality = lowquality_from_placename(location, centroids_only=True)

    # Create marker layers
    grocery_markers = poi_to_markers(grocery, color="#4daf4a", radius=10)
    convenience_markers = poi_to_markers(convenience, color="#377eb8", radius=7)
    lowquality_markers = poi_to_markers(lowquality, color="#e41a1c", radius=5)

    # Set map center based on selected location
    if location == "Albany, NY":
        center = [42.6526, -73.7562]  # Albany, NY coordinates
    elif location == "New York, NY":
        center = [40.7128, -74.0060]  # New York, NY coordinates
    elif location == "Denver, CO":
        center = [39.7392, -104.9903]  # Denver, CO coordinates
    elif location == "Portland, ME":
        center = [43.6591, -70.2568]  # Portland, ME coordinates

    # Create the map with POI markers and GeoJSON layer
    map_component = dl.Map(center=center, zoom=12, children=[
         dl.GeoJSON(data=geojson_data, id='geojson-layer', 
                #    style= {
                #         'fillColor': '#FFEDA0',
                #         'weight': 1,
                #         'opacity': 1,
                #         'color': 'white',
                #         'dashArray': '3',
                #         'fillOpacity': 0.6,
                #     }
                    ),  # Load GeoJSON data directly
        dl.TileLayer(
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            maxZoom=20,
        ),
        dl.LayersControl(
            [
                dl.Overlay(dl.LayerGroup(grocery_markers), name="Groceries", checked=True),
                dl.Overlay(dl.LayerGroup(convenience_markers), name="Convenience", checked=True),
                dl.Overlay(dl.LayerGroup(lowquality_markers), name="Low-quality", checked=True),
            ]
        ),
       
    ], style={'width': '100%', 'height': '600px'})
    
    return map_component

# Dash app setup
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# App layout with dropdown to select location and map
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(html.H1("Grocery Store Explorer", className="text-center mb-4"))
        ),
        dbc.Row(
            dbc.Col(
                dcc.Dropdown(
                    id="location-dropdown",
                    options=[
                        {'label': 'Albany, NY', 'value': 'Albany, NY'},
                        {'label': 'New York, NY', 'value': 'New York, NY'},
                        {'label': 'Denver, CO', 'value': 'Denver, CO'},
                        {'label': 'Portland, ME', 'value': 'Portland, ME'},
                    ],
                    value="Denver, CO",
                    className="mb-4"
                )
            )
        ),
        dbc.Row(
            dbc.Col(html.Div(id="map-container"))
        ),
    ],
    fluid=True
)

# Callback to update the map based on selected location
@app.callback(
    Output("map-container", "children"),
    Input("location-dropdown", "value")
)
def update_map(location):
    return generate_map(location)

# Run the app
if __name__ == "__main__":
    app.run_server()
