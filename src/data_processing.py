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
import igraph as ig
from warnings import warn
import requests

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
    bounds = polygon.bounds
    gdf = gpd.read_file(
        "data/external/svi_tracts_gdb/SVI_2022_US/SVI2022_US_tract.gdb", bbox=bounds
    ).to_crs(epsg=GEODESIC_EPSG)
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
    nodes["grocery"] = nodes.index.isin(
        groceries.sjoin_nearest(
            nodes,
        ).index_right
    )
    return nodes.to_crs(GEODESIC_EPSG)


@timer
def clean_edges(edges):
    edges = edges.copy()
    edges = edges.dropna(axis="columns", thresh=int(len(edges) * 0.95))
    edges = edges.dropna(axis="rows", how="any")
    edges = edges.reset_index(drop=True)
    # pivot out lists before generating dummies and consolidating them
    highway_dummies = pd.get_dummies(edges.highway.explode()).groupby(level=0).sum()
    highway_dummies.columns = [c + "_hwy" for c in highway_dummies.columns]
    edges = edges.join(highway_dummies)

    if "highway" in edges.columns:
        edges = edges.drop(columns=["highway"])
    return edges


@timer
def clean_nodes(nodes):

    # if skip_cols is None:
    #     skip_cols = []
    # else:
    #     skip_cols = [col for col in skip_cols if col not in nodes.columns]
    # retain_data = nodes[skip_cols]
    # nodes = nodes.drop(columns=skip_cols)

    nodes = nodes.drop(
        columns=[
            col
            for col in ["lat", "lon", "index_right", "highway", "ref"]
            if col in nodes.columns
        ]
    )
    nodes = gpd.GeoDataFrame(nodes, geometry="geometry")
    return nodes.replace([np.inf, -np.inf], np.nan).dropna(how="any")


@timer
def reconcile_nodes_edges(nodes, edges):
    complete = set(nodes.index) & set(edges.u) & set(edges.v)

    # Filter both nodes and edges to this complete set
    nodes = nodes[nodes.index.isin(complete)]
    edges = edges[edges.u.isin(complete) & edges.v.isin(complete)]

    return nodes, edges


@timer
def merge_highway_dummies_to_nodes(nodes, edges):
    nodes = nodes.copy()
    highway_cols = [col for col in edges.columns if "_hwy" in col]
    edge_data = edges[["u"] + highway_cols].copy()

    # Group by node (u) and sum the highway types
    node_highways = edge_data.groupby("u")[highway_cols].sum()

    # Join back to nodes

    nodes = nodes.join(node_highways)
    return nodes


@timer
def merge_svi(nodes, svi, svi_fields=["density"]):
    fields = svi_fields.copy()
    if "geometry" not in fields:
        fields.append("geometry")
    nodes = nodes.to_crs(epsg=EQUAL_AREA_EPSG)
    svi = svi.to_crs(epsg=EQUAL_AREA_EPSG)
    svi = svi[fields]
    try:
        nodes = nodes.sjoin(svi, how="left", predicate="within").to_crs(
            epsg=GEODESIC_EPSG
        )
    except Exception as e:
        warn(f"Falling back to spatial join using GEODESIC geometry. {e}")
        nodes = nodes.to_crs(epsg=GEODESIC_EPSG)
        svi = svi.to_crs(epsg=GEODESIC_EPSG)
        nodes.sjoin(svi, how="left", predicate="within")
    return nodes


@timer
def add_grocery_travel_time(graph, igraph=True):
    if igraph:
        return add_grocery_travel_time_igraph(graph)
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
def add_grocery_travel_time_igraph(graph):
    # Convert to igraph
    ig_graph = ig.Graph.from_networkx(graph)

    # For street networks, we want paths TO grocery stores
    # Since we're calculating from grocery stores, use 'in' to respect one-way streets
    mode = "in" if ig_graph.is_directed() else "all"

    # Get the vertex indices of grocery stores
    node_to_idx = {name: idx for idx, name in enumerate(ig_graph.vs["_nx_name"])}
    idx_to_node = {idx: name for name, idx in node_to_idx.items()}
    grocery_indices = [
        node_to_idx[node]
        for node, attr in graph.nodes(data=True)
        if attr.get("grocery", False)
    ]

    if not grocery_indices:
        warn("No grocery stores found in graph!")
        return graph

    # Calculate shortest paths TO grocery stores by calculating backwards
    shortest_paths = ig_graph.shortest_paths(
        source=grocery_indices, weights="travel_time", mode=mode
    )

    # For each node (column), get minimum distance to any grocery store (rows)
    shortest_paths_to_grocery = {
        idx_to_node[j]: min(shortest_paths[i][j] for i in range(len(grocery_indices)))
        for j in range(len(ig_graph.vs))
    }

    # For grocery stores themselves, find distance to nearest OTHER grocery store
    for grocery_idx in grocery_indices:
        node_name = idx_to_node[grocery_idx]
        # Filter distances to all OTHER grocery stores
        other_store_distances = [
            shortest_paths[i][grocery_idx]
            for i in range(len(grocery_indices))
            if grocery_indices[i] != grocery_idx
        ]
        if other_store_distances:
            shortest_paths_to_grocery[node_name] = min(other_store_distances)

    nx.set_node_attributes(graph, shortest_paths_to_grocery, "nearest_grocery_time")
    return graph


@timer
def add_pagerank(graph):
    nx.set_node_attributes(graph, nx.pagerank(graph), "pagerank")
    return graph


@timer
def add_betweenness(graph, k=500):
    # print("start conversion to ig_graph")
    ig_graph = ig.Graph.from_networkx(graph)
    # print("converted to ig_graph")
    btw = ig_graph.betweenness(weights="travel_time", cutoff=k)

    nx.set_node_attributes(graph, dict(zip(graph.nodes(), btw)), "betweenness")
    return graph


@timer
def generate_placenames():
    cities = pd.read_excel(
        "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list2_2023.xlsx",
        skiprows=2,
    )
    cities = cities[~cities["CBSA Title"].isna()]
    cities[cities.duplicated(subset="CBSA Title")]
    placenames = (
        cities["Principal City Name"]
        .str.cat(cities["CBSA Title"].str.slice(-2), ", ")
        .drop_duplicates()
        .to_list()
    )
    return placenames


@timer
def batch_process_cities(placenames):
    places = {}
    N = len(placenames)
    failed_cities = []  # Track failures
    successful_cities = []  # Track successes

    for i, placename in enumerate(placenames):
        print(f"Processing: {i}/{N} - {placename}")
        retries = 3
        retry_delay = 60

        success = False
        for attempt in range(retries):
            try:
                result = data_from_placename(
                    placename,
                    radius_m=10000,
                    buffer=5000,
                    refresh_cache=False,
                    return_dictionary=True,
                )

                # Verify the result before adding
                if result and isinstance(result, dict) and "nodes" in result:
                    places[placename] = result
                    successful_cities.append(placename)
                    print(f"Successfully processed {placename}")
                    success = True
                    break
                else:
                    raise ValueError(f"Invalid result format for {placename}")

            except requests.exceptions.ConnectTimeout:
                if attempt < retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    warn(
                        f"Timeout for {placename}, waiting {wait_time}s before retry {attempt + 1}"
                    )
                    time.sleep(wait_time)
                else:
                    warn(
                        f"Failed to process {placename} after {retries} attempts - Timeout"
                    )

            except ox._errors.InsufficientResponseError as e:
                warn(f"Unable to complete data pull for {placename}: {str(e)}")
                break  # Don't retry

            except Exception as e:
                warn(
                    f"Failed to process {placename} after {retries} attempts - {str(e)}"
                )

        if not success:
            failed_cities.append(placename)

        # Periodic status update
        if (i + 1) % 5 == 0 or i == N - 1:
            print( "\nProgress Update:")
            print(f"Processed: {i + 1}/{N}")
            print(f"Successful: {len(successful_cities)}")
            print(f"Failed: {len(failed_cities)}")
            if failed_cities:
                print(f"Failed cities: {failed_cities}")
            print("\n")

    # Final summary
    print("\nProcessing Complete!")
    print(f"Total cities: {N}")
    print(f"Successfully processed: {len(successful_cities)}")
    print(f"Failed to process: {len(failed_cities)}")
    if failed_cities:
        print("Failed cities:")
        for city in failed_cities:
            print(f"- {city}")

    return places, {"successful": successful_cities, "failed": failed_cities}


@timer
def add_average_to_edge(graph, attribute):
    for u, v, k in graph.edges(keys=True):

        source_value = graph.nodes[u].get(attribute, np.nan)
        target_value = graph.nodes[v].get(attribute, np.nan)
        average_value = (source_value + target_value) / 2
        graph.edges[u, v, k][attribute] = average_value

    return graph


@timer
@disk_cache
def data_from_placename(
    placename, radius_m=10_000, buffer=5_000, return_dictionary=False
):

    results = {}
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

    nodes, edges = ox.graph_to_gdfs(
        street_nx,
    )
    assert (
        not groceries.index.duplicated().any()
    ), "Duplicate indices found in the groceries dataframe"
    assert (
        not svi.index.duplicated().any()
    ), "Duplicate indices found in the groceries dataframe"
    assert (
        not nodes.index.duplicated().any()
    ), "Duplicate indices found in the nodes dataframe"
    assert (
        not edges.index.duplicated().any()
    ), "Duplicate indices found in the edges dataframe"

    # joining sources to nodes
    nodes = merge_grocery(nodes, groceries)
    assert "index_right" not in nodes.columns
    # return nodes
    assert (
        not nodes.index.duplicated().any()
    ), "Duplicate indices found in the nodes dataframe"

    # rebuild graph
    street_nx = ox.convert.graph_from_gdfs(nodes, edges)

    # Shortest grocery travel_times
    street_nx = add_grocery_travel_time(street_nx)

    # Adding pagerank
    street_nx = add_pagerank(street_nx)
    street_nx = add_betweenness(street_nx)
    assert "index_right" not in nodes.columns
    # blending node values for edges
    street_nx = add_average_to_edge(street_nx, "nearest_grocery_time")
    street_nx = add_average_to_edge(street_nx, "pagerank")

    nodes, edges = ox.graph_to_gdfs(street_nx)
    assert "index_right" not in nodes.columns
    # provide filters to get different levels of analysis
    nodes = nodes.assign(aoa=nodes.geometry.within(area_of_analysis))
    nodes = nodes.assign(buffer=~nodes.geometry.within(area_of_analysis))
    # (nodes)
    # print(edges)

    edges = edges.reset_index()
    aoa_nodes = nodes[nodes["aoa"]].index

    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))
    assert "geometry" in nodes.columns
    assert "geometry" in edges.columns

    edges["aoa"] = edges.u.isin(aoa_nodes) & edges.v.isin(aoa_nodes)
    edges["buffer"] = ~(edges.u.isin(aoa_nodes) & edges.v.isin(aoa_nodes))

    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))
    assert "geometry" in nodes.columns
    assert "geometry" in edges.columns
    assert "index_right" not in nodes.columns

    nodes = merge_svi(nodes, svi)

    assert (
        not nodes.index.duplicated().any()
    ), "Duplicate indices found in the nodes dataframe"
    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))
    assert "geometry" in nodes.columns
    assert "geometry" in edges.columns
    # batting cleanup

    # print(f"preclean edge columns:{edges.columns}")
    edges = clean_edges(edges)
    # print(f"preclean node columns:{nodes.columns}")
    nodes = clean_nodes(
        nodes,
    )
    # print(f"prereconcile edge columns:{edges.columns}")
    # print(f"prereconcile node columns:{nodes.columns}")
    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))
    assert "geometry" in nodes.columns
    assert "geometry" in edges.columns
    nodes, edges = reconcile_nodes_edges(nodes, edges)
    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))
    # print(f"pre_dummymerge edge columns:{edges.columns}")
    # print(f"pre_dummymerge node columns:{nodes.columns}")
    nodes = merge_highway_dummies_to_nodes(nodes, edges)
    assert "x" in nodes.columns
    assert "y" in nodes.columns
    # print(f"post_dummymerge edge columns:{edges.columns}")
    # print(f"post_dummymerge node columns:{nodes.columns}")

    # svi["placename"] = placename
    # nodes["placename"] = placename
    # edges["placename"] = placename
    assert "x" in nodes.columns
    assert "y" in nodes.columns
    assert isinstance(nodes, (gpd.GeoDataFrame))
    assert isinstance(edges, (gpd.GeoDataFrame))

    street_nx = ox.graph_from_gdfs(nodes, edges.set_index(["u", "v", "key"]))

    results.update(
        {
            "placename": placename,
            "radius": radius_m,
            "buffer": buffer,
            "aoa": area_of_analysis,
            "query_scope": query_scope,
            "center_lat": center[0],
            "center_lon": center[1],
            "graph": street_nx,
            "grocery": groceries,
            "svi": svi,
            "nodes": nodes,
            "edges": edges,
        }
    )
    if return_dictionary:
        return results
    else:
        return nodes, edges


if __name__ == "__main__":
    data_from_placename("Albany, NY", refresh_cache=True)
