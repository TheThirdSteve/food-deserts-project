import dash
import os
 
import dash_html_components as html
 
 
app = dash.Dash(__name__)
server = app.server
 

l = []
for filename in os.listdir(directory):
    filepath = os.path.join(directory, filename)
    l.append(filepath)

tex = "/n".join(l)

app.layout = html.H1(children=[os.getcwd(), tex])


if __name__ == '__main__':
 
    app.run_server(debug=True)
 
