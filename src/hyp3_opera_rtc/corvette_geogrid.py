import isce3
import numpy as np
from nisar.workflows.geogrid import _grid_size


# 1 arcsec (not using 1.0/3600.0 to avoid repeating decimals)
SECONDS_IN_DEG = 0.0002777


def get_point_epsg(lat, lon):
    """
    Get EPSG code based on latitude and longitude
    coordinates of a point

    Parameters
    ----------
    lat: float
        Latitude coordinate of the point
    lon: float
        Longitude coordinate of the point

    Returns
    -------
    epsg: int
        UTM zone, Polar stereographic (North / South)
    """
    # "Warp" longitude value into [-180.0, 180.0]
    if (lon >= 180.0) or (lon <= -180.0):
        lon = (lon + 180.0) % 360.0 - 180.0

    if lat >= 75.0:
        epsg = 3413
    elif lat <= -75.0:
        epsg = 3031
    elif lat > 0:
        epsg = 32601 + int(np.round((lon + 177) / 6.0))
    elif lat < 0:
        epsg = 32701 + int(np.round((lon + 177) / 6.0))
    else:
        raise ValueError(f'Could not determine EPSG for {lon}, {lat}')
    assert 1024 <= epsg <= 32767, 'Computed EPSG is out of range'
    return epsg


def assign_check_geogrid(geogrid, xmin=None, ymax=None, xmax=None, ymin=None):
    """
    Initialize geogrid with user defined parameters.
    Check the validity of user-defined parameters

    Parameters
    ----------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 object defining the geogrid
    xmin: float
        Geogrid top-left X coordinate
    ymax: float
        Geogrid top-left Y coordinate
    xmax: float
        Geogrid bottom-right X coordinate
    ymin: float
        Geogrid bottom-right Y coordinate

    Returns
    -------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 geogrid initialized with user-defined inputs
    """

    # Check assigned input coordinates and initialize geogrid accordingly
    if xmin is not None:
        current_end_x = geogrid.start_x + geogrid.spacing_x * geogrid.width
        geogrid.start_x = xmin
        geogrid.width = int(np.ceil((current_end_x - xmin) / geogrid.spacing_x))
    # Restore geogrid end point if provided by the user
    if xmax is not None:
        geogrid.width = int(np.ceil((xmax - geogrid.start_x) / geogrid.spacing_x))
    if ymax is not None:
        current_end_y = geogrid.start_y + geogrid.spacing_y * geogrid.length
        geogrid.start_y = ymax
        geogrid.length = int(np.ceil((current_end_y - ymax) / geogrid.spacing_y))
    if ymin is not None:
        geogrid.length = int(np.ceil((ymin - geogrid.start_y) / geogrid.spacing_y))

    return geogrid


def intersect_geogrid(geogrid, xmin=None, ymax=None, xmax=None, ymin=None):
    """
    Return intersected geogrid with user defined parameters.

    Parameters
    ----------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 object defining the geogrid
    xmin: float
        Geogrid top-left X coordinate
    ymax: float
        Geogrid top-left Y coordinate
    xmax: float
        Geogrid bottom-right X coordinate
    ymin: float
        Geogrid bottom-right Y coordinate

    Returns
    -------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 geogrid
    """

    if xmin is not None and xmin > geogrid.start_x:
        current_end_x = geogrid.start_x + geogrid.spacing_x * geogrid.width
        geogrid.start_x = xmin
        geogrid.width = int(np.ceil((current_end_x - xmin) / geogrid.spacing_x))

    if xmax is not None and (xmax < geogrid.start_x + geogrid.width * geogrid.spacing_x):
        geogrid.width = int(np.ceil((xmax - geogrid.start_x) / geogrid.spacing_x))
    if ymax is not None and ymax < geogrid.start_y:
        current_end_y = geogrid.start_y + geogrid.spacing_y * geogrid.length
        geogrid.start_y = ymax
        geogrid.length = int(np.ceil((current_end_y - ymax) / geogrid.spacing_y))

    if ymin is not None and (ymin > geogrid.start_y + geogrid.length * geogrid.spacing_y):
        geogrid.length = int(np.ceil((ymin - geogrid.start_y) / geogrid.spacing_y))

    return geogrid


def check_snap_values(x_snap, y_snap, x_spacing, y_spacing):
    """
    Check validity of snap values

    Parameters
    ----------
    x_snap: float
        Snap value along X-direction
    y_snap: float
        Snap value along Y-direction
    x_spacing: float
        Spacing of the geogrid along X-direction
    y_spacing: float
        Spacing of the geogrid along Y-direction
    """

    # Check that snap values in X/Y-directions are positive
    if x_snap is not None and x_snap <= 0:
        err_str = f'Snap value in X direction must be > 0 (x_snap: {x_snap})'
        raise ValueError(err_str)
    if y_snap is not None and y_snap <= 0:
        err_str = f'Snap value in Y direction must be > 0 (y_snap: {y_snap})'
        raise ValueError(err_str)

    # Check that snap values in X/Y are integer multiples of the geogrid
    # spacings in X/Y directions
    if x_snap is not None and x_snap % x_spacing != 0.0:
        err_str = 'x_snap must be exact multiple of spacing in X direction (x_snap % x_spacing !=0)'
        raise ValueError(err_str)
    if y_snap is not None and y_snap % y_spacing != 0.0:
        err_str = 'y_snap must be exact multiple of spacing in Y direction (y_snap % y_spacing !=0)'
        raise ValueError(err_str)


def snap_coord(val, snap, round_func):
    """
    Returns the snapped values of the input value

    Parameters
    -----------
    val : float
        Input value to snap
    snap : float
        Snapping step
    round_func : function pointer
        A function used to round `val` i.e. round, ceil, floor

    Return:
    --------
    snapped_value : float
        snapped value of `var` by `snap`

    """
    snapped_value = round_func(float(val) / snap) * snap
    return snapped_value


def snap_geogrid(geogrid, x_snap, y_snap):
    """
    Snap geogrid based on user-defined snapping values

    Parameters
    ----------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 object definining the geogrid
    x_snap: float
        Snap value along X-direction
    y_snap: float
        Snap value along Y-direction

    Returns
    -------
    geogrid: isce3.product.GeoGridParameters
        ISCE3 object containing the snapped geogrid
    """
    xmax = geogrid.start_x + geogrid.width * geogrid.spacing_x
    ymin = geogrid.start_y + geogrid.length * geogrid.spacing_y

    if x_snap is not None:
        geogrid.start_x = snap_coord(geogrid.start_x, x_snap, np.floor)
        end_x = snap_coord(xmax, x_snap, np.ceil)
        geogrid.width = _grid_size(end_x, geogrid.start_x, geogrid.spacing_x)
    if y_snap is not None:
        geogrid.start_y = snap_coord(geogrid.start_y, y_snap, np.ceil)
        end_y = snap_coord(ymin, y_snap, np.floor)
        geogrid.length = _grid_size(end_y, geogrid.start_y, geogrid.spacing_y)
    return geogrid


def generate_geogrids(bursts, geo_dict, mosaic_dict, opts):
    """
    Compute frame and bursts geogrids

    Parameters
    ----------
    bursts: list[s1reader.s1_burst_slc.Sentinel1BurstSlc]
        List of S-1 burst SLC objects
    geo_dict: dict
        Dictionary containing runconfig processing.geocoding
        parameters
    mosaic_dict: dict
        Dictionary containing runconfig processing.mosaicking
        parameters

    Returns
    -------
    geogrid_all_snapped: isce3.product.GeoGridParameters
        Mosaic geogrid
    geogrids_dict: dict
        Dict containing bursts' geogrids indexed by burst_id
    """
    mosaic_geogrid_dict = mosaic_dict['mosaic_geogrid']
    epsg_mosaic = opts.output_epsg
    xmin_mosaic = mosaic_geogrid_dict['top_left']['x']
    ymax_mosaic = mosaic_geogrid_dict['top_left']['y']
    x_spacing_mosaic = mosaic_geogrid_dict['x_posting']
    y_spacing_positive_mosaic = mosaic_geogrid_dict['y_posting']
    xmax_mosaic = mosaic_geogrid_dict['bottom_right']['x']
    ymin_mosaic = mosaic_geogrid_dict['bottom_right']['y']
    x_snap_mosaic = mosaic_geogrid_dict['x_snap']
    y_snap_mosaic = mosaic_geogrid_dict['y_snap']

    bursts_geogrid_dict = geo_dict['bursts_geogrid']
    epsg_bursts = bursts_geogrid_dict['output_epsg']
    xmin_bursts = bursts_geogrid_dict['top_left']['x']
    ymax_bursts = bursts_geogrid_dict['top_left']['y']
    x_spacing_bursts = bursts_geogrid_dict['x_posting']
    y_spacing_positive_bursts = bursts_geogrid_dict['y_posting']
    xmax_bursts = bursts_geogrid_dict['bottom_right']['x']
    ymin_bursts = bursts_geogrid_dict['bottom_right']['y']
    x_snap_bursts = bursts_geogrid_dict['x_snap']
    y_snap_bursts = bursts_geogrid_dict['y_snap']

    xmin_all_bursts = np.inf
    ymax_all_bursts = -np.inf
    xmax_all_bursts = -np.inf
    ymin_all_bursts = np.inf

    burst = bursts['t115_245714_iw1']['VV']

    # Compute mosaic and burst EPSG codes if not assigned in runconfig
    if epsg_mosaic is None:
        epsg_mosaic = get_point_epsg(burst.center.y, burst.center.x)
    epsg_bursts = epsg_mosaic
    y_spacing_mosaic = -1 * y_spacing_positive_mosaic
    y_spacing_bursts = -1 * y_spacing_positive_bursts

    geogrids_dict = {}
    for burst_id, burst_pol in bursts.items():
        pol_list = list(burst_pol.keys())
        burst = burst_pol[pol_list[0]]
        if burst_id in geogrids_dict.keys():
            continue

        radar_grid = burst.as_isce3_radargrid()
        orbit = burst.orbit

        geogrid_burst = None
        if len(bursts) > 1 or None in [xmin_bursts, ymax_bursts, xmax_bursts, ymin_bursts]:
            # Initialize geogrid with estimated boundaries
            geogrid_burst = isce3.product.bbox_to_geogrid(
                radar_grid, orbit, isce3.core.LUT2d(), x_spacing_bursts, y_spacing_bursts, epsg_bursts
            )

            if len(bursts) == 1 and None in [xmin_bursts, ymax_bursts, xmax_bursts, ymin_bursts]:
                # Check and further initialize geogrid
                geogrid_burst = assign_check_geogrid(geogrid_burst, xmin_bursts, ymax_bursts, xmax_bursts, ymin_bursts)
            geogrid_burst = intersect_geogrid(geogrid_burst, xmin_bursts, ymax_bursts, xmax_bursts, ymin_bursts)
        else:
            # If all the start/end coordinates have been assigned,
            # initialize the geogrid with them
            width = _grid_size(xmax_bursts, xmin_bursts, x_spacing_bursts)
            length = _grid_size(ymin_bursts, ymax_bursts, y_spacing_bursts)
            geogrid_burst = isce3.product.GeoGridParameters(
                xmin_bursts, ymax_bursts, x_spacing_bursts, y_spacing_bursts, width, length, epsg_bursts
            )

        # Check snap values
        check_snap_values(x_snap_bursts, y_snap_bursts, x_spacing_bursts, y_spacing_bursts)
        # Snap coordinates
        geogrid_snapped = snap_geogrid(geogrid_burst, x_snap_bursts, y_snap_bursts)

        xmin_all_bursts = min([xmin_all_bursts, geogrid_snapped.start_x])
        ymax_all_bursts = max([ymax_all_bursts, geogrid_snapped.start_y])
        xmax_all_bursts = max(
            [xmax_all_bursts, geogrid_snapped.start_x + geogrid_snapped.spacing_x * geogrid_snapped.width]
        )
        ymin_all_bursts = min(
            [ymin_all_bursts, geogrid_snapped.start_y + geogrid_snapped.spacing_y * geogrid_snapped.length]
        )

        geogrids_dict[burst_id] = geogrid_snapped

    if xmin_mosaic is None:
        xmin_mosaic = xmin_all_bursts
    if ymax_mosaic is None:
        ymax_mosaic = ymax_all_bursts
    if xmax_mosaic is None:
        xmax_mosaic = xmax_all_bursts
    if ymin_mosaic is None:
        ymin_mosaic = ymin_all_bursts

    width = _grid_size(xmax_mosaic, xmin_mosaic, x_spacing_mosaic)
    length = _grid_size(ymin_mosaic, ymax_mosaic, y_spacing_mosaic)
    geogrid_all = isce3.product.GeoGridParameters(
        xmin_mosaic, ymax_mosaic, x_spacing_mosaic, y_spacing_mosaic, width, length, epsg_mosaic
    )

    # Check snap values
    check_snap_values(x_snap_mosaic, y_snap_mosaic, x_spacing_mosaic, y_spacing_mosaic)

    # Snap coordinates
    geogrid_all_snapped = snap_geogrid(geogrid_all, x_snap_mosaic, y_snap_mosaic)
    return geogrid_all_snapped, geogrids_dict
