import dash
import os
import json
 
import dash_html_components as html
 
 
app = dash.Dash(__name__)
server = app.server

geojson_path = 'geo_json_test.json'
with open(geojson_path) as f:
    geojson_data = json.load(f)
 
current_dir = os.getcwd()
l = []
for filename in os.listdir(current_dir):
    filepath = os.path.join(current_dir, filename)
    l.append(filepath)

tex = "\n".join(l)

app.layout = html.H1(children=[os.getcwd(), tex, geojson_data])


if __name__ == '__main__':
 
    app.run_server(debug=True)
 
