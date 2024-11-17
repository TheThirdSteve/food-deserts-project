import osmnx as ox
import geopandas as gpd
from functools import cache
from shapely.geometry import Point
from geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry
import os
import sys

ox.settings.requests_timeout = 60

# Tag definitions
PRIMARY = {"shop": "supermarket"}
SECONDARY = [{"shop": "general"}, {"shop": "convenience"}, {"shop": "greengrocer"}]
TERTIARY = [
    {"amenity": "fast_food"},
    {"shop": "variety_store"},
    {"amenity": "fuel"},
]

GEODESIC_EPSG = 4326
CARTESIAN_EPSG = 32633
if os.getcwd().endswith("notebooks") or os.getcwd().endswith("src"):
    os.chdir("..")

if "src" not in sys.path:
    sys.path.append("src")


def _make_hashable_tags_helper(tags: dict | list[dict]) -> frozenset:
    """
    Convert a dictionary or list of dictionaries of tags into a hashable type (frozenset of tuples).
    This allows the cache function to work properly.

    Args:
        tags (dict | list[dict]): Tags to be converted.

    Returns:
        frozenset: Hashable representation of the tags.
    """
    if isinstance(tags, dict):
        return frozenset(tags.items())
    elif isinstance(tags, list):
        combined_tags = {}
        for tag in tags:
            for key, value in tag.items():
                if key in combined_tags:
                    if isinstance(combined_tags[key], list):
                        combined_tags[key].append(value)
                    else:
                        combined_tags[key] = [combined_tags[key], value]
                else:
                    combined_tags[key] = value
        return frozenset(
            (key, tuple(value) if isinstance(value, list) else value)
            for key, value in combined_tags.items()
        )
    else:
        raise ValueError("Tags must be a dictionary or a list of dictionaries.")


# @cache
def _from_place_name_helper(placename: str, hashable_tags: frozenset) -> GeoDataFrame:
    """
    Cached function to store POI results based on place name and hashable tags.

    Args:
        placename (str): Name of the place.
        hashable_tags (frozenset): Hashable representation of tags.

    Returns:
        GeoDataFrame: GeoDataFrame containing the POI results.
    """
    tags = {key: value for key, value in hashable_tags}
    tags = {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in tags.items()
    }
    
    return ox.features_from_place(placename, tags=tags)


# @cache
def _from_point_helper(
    lat: float, lon: float, radius_m: int, hashable_tags: frozenset
) -> GeoDataFrame:
    """
    Cached function to retrieve OSM features within a circular area based on tags.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        radius_m (int): Radius in meters.
        hashable_tags (frozenset): Hashable representation of tags.

    Returns:
        GeoDataFrame: GeoDataFrame containing the OSM features.
    """
    polygon = create_circular_polygon(lat=lat, lon=lon, radius_m=radius_m)
    tags = {key: value for key, value in hashable_tags}
    tags = {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in tags.items()
    }
    return ox.features_from_polygon(polygon, tags=tags)


def get_centroids(gdf_polygons: GeoDataFrame) -> GeoDataFrame:
    """
    Calculate the centroids of the geometries in a GeoDataFrame.

    Args:
        gdf_polygons (GeoDataFrame): GeoDataFrame containing the geometries.

    Returns:
        GeoDataFrame: GeoDataFrame containing the centroids.
    """
    if gdf_polygons.crs is None:
        raise ValueError(
            "GeoDataFrame has no CRS. Please set the CRS before calculating centroids."
        )
    original_projection = gdf_polygons.crs
    gdf_projected = gdf_polygons.to_crs(epsg=CARTESIAN_EPSG)
    centroids = gdf_projected.centroid.to_crs(original_projection)
    return centroids


def encircle_place(placename):
    """
    Generates a minimum bounding circle around a given place.
    Parameters:
    placename (str): The name of the place to encircle.
    Returns:
    gdf_circle (GeoDataFrame): A GeoDataFrame containing the minimum bounding circle of the place.
    """

    gdf_polygon = ox.geocode_to_gdf(placename)
    crs = gdf_polygon.crs
    gdf_circle = (
        gdf_polygon.geometry.to_crs(CARTESIAN_EPSG)
        .minimum_bounding_circle()
        .to_frame()
        .to_crs(crs)
    )
    return gdf_circle


def create_circular_polygon(
    lat: float = None, lon: float = None, point: Point = None, radius_m: int = 10_000
) -> BaseGeometry:
    """
    Creates a circular polygon around a given point on the Earth's surface using GeoPandas.
    Note: This function does not execute a query. It utilizes geographic libraries for their
    projection utilities.
    Args:
        lat (float, optional): Latitude of the center point. Defaults to None.
        lon (float, optional): Longitude of the center point. Defaults to None.
        point (Point, optional): Shapely Point object. Defaults to None.
        radius_m (int, optional): Radius in meters. Defaults to 10_000.

    Returns:
        BaseGeometry: Circular polygon geometry.
    """
    if lat is not None and lon is not None:
        point = Point(lon, lat)
    elif point is not None:
        lon, lat = point.x, point.y
    else:
        raise ValueError("You must provide either lat/lon or a Point object.")

    gdf = gpd.GeoDataFrame(index=[0], crs=f"EPSG:{GEODESIC_EPSG}", geometry=[point])
    aeqd_proj = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m +ellps=WGS84"
    gdf_projected = gdf.to_crs(aeqd_proj)
    gdf_projected["geometry"] = gdf_projected.buffer(radius_m)
    gdf_buffer = gdf_projected.to_crs(f"EPSG:{GEODESIC_EPSG}")
    return gdf_buffer["geometry"].iloc[0]


def groceries_from_placename(
    placename: str, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve grocery POIs from a place name.

    Args:
        placename (str): Name of the place.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the grocery POIs.
    """
    gdf = _from_place_name_helper(placename, _make_hashable_tags_helper(PRIMARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Grocery"
    return gdf


def convenience_from_placename(
    placename: str, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve convenience store POIs from a place name.

    Args:
        placename (str): Name of the place.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the convenience store POIs.
    """
    gdf = _from_place_name_helper(placename, _make_hashable_tags_helper(SECONDARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Convenience"
    return gdf


def lowquality_from_placename(
    placename: str, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve low-quality food POIs from a place name.

    Args:
        placename (str): Name of the place.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the low-quality food POIs.
    """
    gdf = _from_place_name_helper(placename, _make_hashable_tags_helper(TERTIARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Low Quality"
    return gdf


def groceries_from_point(
    lat: float, lon: float, radius_m: int = 10_000, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve grocery POIs from a point and radius.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        radius_m (int, optional): Radius in meters. Defaults to 10_000.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the grocery POIs.
    """

    gdf = _from_point_helper(lat, lon, radius_m, _make_hashable_tags_helper(PRIMARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Grocery"
    return gdf


def convenience_from_point(
    lat: float, lon: float, radius_m: int = 10_000, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve convenience store POIs from a point and radius.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        radius_m (int, optional): Radius in meters. Defaults to 10_000.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the convenience store POIs.
    """

    gdf = _from_point_helper(lat, lon, radius_m, _make_hashable_tags_helper(SECONDARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Convenience"
    return gdf


def lowquality_from_point(
    lat: float, lon: float, radius_m: int = 10_000, centroids_only: bool = True
) -> GeoDataFrame:
    """
    Retrieve low-quality food POIs from a point and radius.

    Args:
        lat (float): Latitude of the center point.
        lon (float): Longitude of the center point.
        radius_m (int, optional): Radius in meters. Defaults to 10_000.
        centroids_only (bool, optional): Whether to return centroids only. Defaults to True.

    Returns:
        GeoDataFrame: GeoDataFrame containing the low-quality food POIs.
    """

    gdf = _from_point_helper(lat, lon, radius_m, _make_hashable_tags_helper(TERTIARY))
    if centroids_only:
        gdf["geometry"] = get_centroids(gdf)
    gdf["label"] = "Low Quality"
    return gdf


def place_to_point(placename):
    point = ox.geocode(placename)
    return point


def place_to_polygon(placename):
    polygon = ox.geocode_to_gdf(placename)
    return polygon