
import osmnx as ox
import networkx as nx
from networkx.exception import NetworkXPointlessConcept
from shapely import centroid
import os
import sys
from shapely import Point
import geopandas as gpd
import warnings 

GEODESIC_EPSG = 4326
EQUAL_AREA_EPSG = 5070

if os.getcwd().endswith("notebooks") or os.getcwd().endswith("src"):
    os.chdir("..")

if "src" not in sys.path:
    sys.path.append("src")
from poi_queries import create_circular_polygon


def key_to_max(dictionary: dict) -> any:
    """
    Takes a dictionary and finds the maximum value.
    Returns the key for that value.

    Args:
        dictionary (dict): The dictionary to search.

    Returns:
        any: The key corresponding to the maximum value in the dictionary.

    Raises:
        ValueError: If the dictionary is empty.
    """
    if not dictionary:
        raise ValueError("The dictionary is empty. Cannot determine maximum key.")
    return max(dictionary, key=lambda idx: dictionary[idx])


# def busiest_intersection(polygon, precomputed_graph=None):
#     """
#     Takes a polygon and tries to determine the busiest intersection.

#     Optionally, it can take a precomputed graph to prevent spamming
#     openstreetmaps with queries.

#     In the event that no graph can be determined, it tries to find
#     a drivable point within near the center of the shape.


#     Returns:
#         _type_: _description_
#     """

#     # Take G as input or seek it out
#     if precomputed_graph is not None:
#         G = precomputed_graph
#     else:
#         G = road_graph(polygon)

#     # Check G again

#     if G is not None:

#         weights = dict(G.degree())
#         busiest = G.nodes[key_to_max(weights)]

#         return ox.utils_geo.Point((busiest["y"], busiest["x"]))

#     elif G is None:
#         return fallback_point(polygon)


def fallback_point(polygon):
    """
    Function for getting the centroid of a polygon. Useful for finding an
    arbitrary point when there's no viable point within the geometry.

    Args:
        polygon (_type_): _description_

    Returns:
        _type_: _description_
    """

    point = centroid(polygon)
    return point


def road_network_from_polygon(polygon) -> nx.MultiDiGraph:
    """
    Takes a polygon (expects a geopandas geometry object) and queries the
    osmnx API for the network of roads within the polygon.

    If the graph is empty, it returns None.

    Args:
        polygon (geopandas.GeoSeries or shapely.geometry.Polygon): The input polygon to query the road network.

    Returns:
        nx.MultiDiGraph: The road network graph or None if no graph is available.
    """

    if isinstance(polygon, gpd.GeoDataFrame):
        polygon = polygon.to_crs(epsg=GEODESIC_EPSG)
        polygon = polygon.geometry[0]
    try:
        # filters the highway field using regex (removes service roads)
        custom_filter = (
            '["highway"~"motorway|trunk|primary|secondary|tertiary|residential"]'
        )
        G = ox.graph_from_polygon(
            polygon,
            network_type="drive",
            simplify=True,
            retain_all=False,
            custom_filter=custom_filter,
        )
        G = ox.project_graph(G, EQUAL_AREA_EPSG)
        # G = ox.simplification.simplify_graph(G)
        G = ox.consolidate_intersections(G)
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
        G = ox.project_graph(G, to_crs=GEODESIC_EPSG)

        return G

    except NetworkXPointlessConcept:
        warnings.warn("No streets or roads could be found in the boundary")
        return None  # Return None explicitly for clarity.


def road_network_from_point(
    lat: float = None, lon: float = None, point: Point = None, radius_m: int = 10_000
):
    circle = create_circular_polygon(lat=lat, lon=lon, point=point, radius_m=radius_m)

    G = road_network_from_polygon(circle)
    return G


def add_binary_attribute(G, node_subset, attribute_label):
    """
    Adds a binary attribute to the nodes in the graph.

    Args:
         G (networkx.Graph): The graph to which the attribute will be added.
         node_subset (set): A subset of nodes to be marked with the attribute.
         attribute_label (str): The name of the attribute to be added.

     Returns:
         networkx.Graph: The graph with the added binary attribute.
    """
    for node in G.nodes:
        G.nodes[node][attribute_label] = node in node_subset
    return G