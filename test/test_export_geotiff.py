import os
import time

import ee
import pytest
import rasterio as rio
from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsRectangle,
)

from ee_plugin import Map
from ee_plugin.processing.export_geotiff import ExportGeoTIFFAlgorithm


def test_layer_not_found():
    alg = ExportGeoTIFFAlgorithm()
    alg.initAlgorithm(config=None)
    alg.raster_layers = []  # Ensure no layers exist for selection
    params = {
        "EE_IMAGE": 0,
        "EXTENT": None,  # Missing extent
        "SCALE": 1000,
        "PROJECTION": "EPSG:4326",
        "OUTPUT": "test.tif",
    }

    with pytest.raises(IndexError):  # Expect IndexError due to empty list
        alg.processAlgorithm(
            params, context=QgsProcessingContext(), feedback=QgsProcessingFeedback()
        )


def test_requires_extent():
    img = ee.Image("USGS/SRTMGL1_003")
    Map.addLayer(img, {}, "DEM")  # Add a layer to the map

    alg = ExportGeoTIFFAlgorithm()
    alg.initAlgorithm(config=None)

    out_path = "test.tif"

    params = {
        "EE_IMAGE": 0,
        "EXTENT": None,  # Missing extent
        "SCALE": 1000,
        "PROJECTION": "EPSG:4326",
        "OUTPUT": out_path,
    }

    with pytest.raises(ValueError):
        alg.processAlgorithm(
            params, context=QgsProcessingContext(), feedback=QgsProcessingFeedback()
        )


@pytest.mark.parametrize(
    "crs, scale, extent",
    [
        ("EPSG:4326", 1000, (-123.5, 49.5, -123.0, 50.0)),  # WGS 84
        ("EPSG:4326", 5000, (-130.0, 45.0, -120.0, 55.0)),  # WGS 84
        ("EPSG:3857", 1000, (-13700, 6300, -13650, 6350)),  # Web Mercator
        ("EPSG:3857", 5000, (-13720, 6305, -13680, 6355)),  # Web Mercator
        ("EPSG:32610", 1000, (5000, 54750, 5050, 54850)),  # UTM Zone 10N
        ("EPSG:32610", 5000, (5100, 54000, 5150, 54100)),  # UTM Zone 10N
    ],
)
def test_varied_params_export(crs, scale, extent):
    time.sleep(1)  # connection pool can get full
    img = ee.Image("USGS/SRTMGL1_003")
    Map.addLayer(img, {}, "DEM")  # Add a layer to the map
    alg = ExportGeoTIFFAlgorithm()
    alg.initAlgorithm(config=None)

    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    alg.raster_layers = ["DEM"]

    out_path = f"test_{crs}_{scale}.tif"

    extent_rect = QgsRectangle(*extent)

    params = {
        "EE_IMAGE": 0,
        "EXTENT": extent_rect,
        "SCALE": scale,
        "PROJECTION": crs,
        "OUTPUT": out_path,
    }

    alg.processAlgorithm(params, context=context, feedback=feedback)

    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0

    with rio.open(out_path) as ds:
        assert ds.count == 1, "Unexpected number of bands"
        assert ds.width > 0 and ds.height > 0, "Invalid raster size"

    os.remove(out_path)


def test_extent_transformed_to_target_crs():
    """Ensure extent is transformed correctly from EPSG:3857 to EPSG:4326 before export."""

    # Add a layer reprojected to EPSG:3857 (Web Mercator)
    img = ee.Image("USGS/SRTMGL1_003").reproject("EPSG:3857", None, 30)
    Map.addLayer(img, {}, "DEM_WEB")

    alg = ExportGeoTIFFAlgorithm()
    alg.initAlgorithm(config=None)

    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    alg.raster_layers = ["DEM_WEB"]

    # The original layer is in EPSG:3857 (meters); extent should be in meters
    # Let's take a small area in meters around Vancouver
    extent_3857 = "-13700000,-13680000,6300000,6320000 [EPSG:3857]"

    out_path = "test_extent_transformed.tif"
    params = {
        "EE_IMAGE": 0,
        "EXTENT": extent_3857,
        "SCALE": 30,
        "PROJECTION": "EPSG:4326",
        "OUTPUT": out_path,
    }

    alg.processAlgorithm(params, context=context, feedback=feedback)

    with rio.open(out_path) as ds:
        assert (
            ds.width < 5000 and ds.height < 5000
        ), "Raster size indicates extent not transformed correctly"
        assert (
            "WGS 84" in ds.crs.to_wkt() or "4326" in ds.crs.to_string()
        ), f"Unexpected CRS: {ds.crs}"
        assert ds.count == 1

    os.remove(out_path)
