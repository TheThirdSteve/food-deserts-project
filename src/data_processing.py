from functools import reduce, cache, wraps
import pandas as pd
import geopandas as gpd
import osmnx as ox
import networkx as nx
import os
import sys
from pathlib import Path
import operator
import numpy as np
import time
import hashlib
import pickle

GEODESIC_EPSG = 4326
EQUAL_AREA_EPSG = 5070

# operate from root directory
if os.getcwd().endswith("notebooks") or os.getcwd().endswith("src"):
    os.chdir("..")

if "src" not in sys.path:
    sys.path.append("src")

from street_networks import road_network_from_polygon
from poi_queries import create_circular_polygon


def timer(func):
    """A utility function to to print the runtime of the decorated function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()  # Record the start time
        result = func(*args, **kwargs)  # Call the original function
        end_time = time.perf_counter()  # Record the end time
        duration = end_time - start_time  # Calculate the duration
        string_args = [arg for arg in args if isinstance(arg, str)]
        print(
            f"Function '{func.__name__}, {string_args}' executed in {duration:.4f} seconds"
        )
        return result  # Return the result of the original function

    return wrapper


def disk_cache(func):
    """Simple disk cache decorator with hardcoded cache directory"""
    cache_path = Path("data", "processed", "cache")  # caching path
    cache_path.mkdir(exist_ok=True)  # ok to make directory if missing

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Create cache key from function name and arguments
        key_parts = [func.__name__, str(args), str(sorted(kwargs.items()))]
        key = hashlib.md5(str(key_parts).encode()).hexdigest()
        cache_file = cache_path / f"{key}.pickle"  # lookup hash of filename

        # Check if cache exists
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    return pickle.load(f)  # early return from file
            except Exception as e:
                print(f"Cache error: {e}")

        # Cache miss - compute and store result
        result = func(*args, **kwargs)
        with open(cache_file, "wb") as f:
            pickle.dump(result, f)  # if it doesn't exist, save it with hash name

        return result

    return wrapper


def iterable_from_keys(df, *key_fields):
    """
    Create an iterator from a dataframe and an arbitrary sequence of key fields.
    Each iteration yields a chunk from the dataframe using the keys (similar to a groupby).
    Used to break up a dataframe for incremental processing when groupby => transform
    doesn't do what you need.
    """

    for iter_key in (
        df[[f for f in key_fields]].drop_duplicates().itertuples(index=False)
    ):
        conditions = (df[field] == getattr(iter_key, field) for field in key_fields)
        filter = reduce(operator.and_, conditions)
        yield df[filter]


@timer
@cache
def read_svi(polygon):
    gdf = gpd.read_file("data/external/svi_tracts_gdb/SVI2022_US_tract.gdb").to_crs(
        epsg=GEODESIC_EPSG
    )
    gdf = gdf[gdf.geometry.intersects(polygon)]
    gdf["density"] = gdf["E_TOTPOP"] / gdf["AREA_SQMI"]

    return gdf


@timer
@cache
def fetch_graph(polygon):
    G = road_network_from_polygon(polygon)
    return G


@timer
@cache
def fetch_groceries(polygon):
    groceries = ox.features_from_polygon(
        polygon, tags={"shop": "supermarket"}
    ).reset_index()

    groceries = groceries[["osmid", "geometry"]].assign(grocery=True)
    return groceries


@timer
def merge_grocery(nodes, groceries):
    nodes = nodes.to_crs(epsg=EQUAL_AREA_EPSG)
    groceries = groceries.to_crs(epsg=EQUAL_AREA_EPSG)

    # Perform sjoin_nearest with projected CRS to get Euclidean distance
    joined = nodes.sjoin_nearest(groceries, how="left", distance_col="euclidean")
    nearest_groceries = joined.loc[joined.groupby("osmid_right")["euclidean"].idxmin()]
    nearest_groceries.index.names = ["osmid"]
    nodes = nodes.merge(
        nearest_groceries["grocery"], how="left", left_index=True, right_index=True
    ).fillna({"grocery": False})
    nodes = nodes.merge(
        joined["euclidean"], how="inner", left_index=True, right_index=True
    )
    return nodes.to_crs(GEODESIC_EPSG)


@timer
def merge_svi(nodes, svi):
    return (
        nodes.to_crs(EQUAL_AREA_EPSG)
        .sjoin(svi.to_crs(EQUAL_AREA_EPSG), how="left")
        .to_crs(GEODESIC_EPSG)
    )


@timer
def add_grocery_travel_time(graph):
    grocery_node_ids = [
        node for node, attr in graph.nodes(data=True) if attr.get("grocery", False)
    ]

    shortest_paths_to_grocery = nx.multi_source_dijkstra_path_length(
        graph, sources=grocery_node_ids, weight="travel_time"
    )

    # Replace zero distances with distance to nearest other grocery store
    for node in grocery_node_ids:
        # If this node has a zero distance (distance to itself)
        if shortest_paths_to_grocery[node] == 0:
            # Calculate paths from this specific node
            shortest_paths = nx.single_source_dijkstra_path_length(
                graph, node, weight="travel_time"
            )

            # Get distances to other grocery nodes only
            non_self_distances = {
                target: dist
                for target, dist in shortest_paths.items()
                if target in grocery_node_ids and target != node
            }

            # Replace the zero distance with distance to nearest other grocery store
            if non_self_distances:
                shortest_paths_to_grocery[node] = min(non_self_distances.values())
    nx.set_node_attributes(graph, shortest_paths_to_grocery, "nearest_grocery_time")
    return graph


@timer
def add_average_to_edge(graph, attribute):
    for u, v, k in graph.edges(keys=True):

        source_value = graph.nodes[u].get(attribute, np.nan)
        target_value = graph.nodes[v].get(attribute, np.nan)
        average_value = (source_value + target_value) / 2
        graph.edges[u, v, k][attribute] = average_value

    return graph


@timer
def add_pagerank(graph):
    nx.set_node_attributes(graph, nx.pagerank(graph), "pagerank")
    return graph


@timer
@disk_cache
def data_from_placename(placename, radius_m=10_000, buffer=5_000):

    center = ox.geocode(placename)

    area_of_analysis = create_circular_polygon(
        lat=center[0], lon=center[1], radius_m=radius_m
    )
    query_scope = create_circular_polygon(
        lat=center[0], lon=center[1], radius_m=radius_m + buffer
    )

    # three sources, two queries, one read from file
    groceries = fetch_groceries(query_scope)

    street_nx = fetch_graph(query_scope)

    svi = read_svi(query_scope)

    nodes, edges = ox.convert.graph_to_gdfs(street_nx)

    # joining sources to nodes
    nodes = merge_grocery(nodes, groceries)
    nodes = merge_svi(nodes, svi)

    # rebuild graph
    street_nx = ox.convert.graph_from_gdfs(nodes, edges)

    # Shortest grocery travel_times
    street_nx = add_grocery_travel_time(street_nx)

    # Adding pagerank
    street_nx = add_pagerank(street_nx)

    # blending node values for edges
    street_nx = add_average_to_edge(street_nx, "nearest_grocery_time")
    street_nx = add_average_to_edge(street_nx, "pagerank")

    nodes, edges = ox.graph_to_gdfs(street_nx)

    # tagging area of analysis with the aoa variable
    nodes["aoa"] = nodes.geometry.within(area_of_analysis)
    edges = edges.reset_index()
    edges["aoa"] = edges.u.isin(nodes[nodes.aoa].index) | edges.v.isin(
        nodes[nodes.aoa].index
    )
    # Filter from query scope down to area of analysis
    nodes["buffer"] = ~nodes.geometry.within(area_of_analysis)
    edges = edges.reset_index()
    edges["aoa"] = ~edges.u.isin(nodes[nodes.aoa].index) | edges.v.isin(
        nodes[nodes.aoa].index
    )
    # add percentile columns for greater variance

    return nodes, edges


