import logging
import os
import time
from dataclasses import dataclass

import isce3
import numpy as np
import yaml
from osgeo import gdal
from rtc.runconfig import RunConfig
from s1reader.s1_burst_slc import Sentinel1BurstSlc
from scipy import ndimage


logger = logging.getLogger('rtc_s1')

STATIC_LAYERS_LAYOVER_SHADOW_MASK_MULTILOOK_FACTOR = 3
STATIC_LAYERS_AZ_MARGIN = 1.2
STATIC_LAYERS_RG_MARGIN = 0.2

LAYER_NAME_LAYOVER_SHADOW_MASK = 'mask'
LAYER_NAME_RTC_ANF_GAMMA0_TO_SIGMA0 = 'rtc_anf_gamma0_to_sigma0'
LAYER_NAME_NUMBER_OF_LOOKS = 'number_of_looks'
LAYER_NAME_INCIDENCE_ANGLE = 'incidence_angle'
LAYER_NAME_LOCAL_INCIDENCE_ANGLE = 'local_incidence_angle'
LAYER_NAME_PROJECTION_ANGLE = 'projection_angle'
LAYER_NAME_RTC_ANF_PROJECTION_ANGLE = 'rtc_anf_projection_angle'
LAYER_NAME_RANGE_SLOPE = 'range_slope'
LAYER_NAME_DEM = 'interpolated_dem'


# from geogrid.py
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


# from rtc_s1.py
def set_dict_item_recursive(dict_in, list_path, val):
    """
    - Recursively locate the key in `dict_in`,
      whose path is provided in the list of keys.
    - Add or update the value of the located key of `dict_in`
    - Create the key in `dict_in` with empty dict when the key does not exist

    Parameters
    ----------
    dict_in: dict
        Dict to update
    list_path: list
        Path to the item in the multiple layer of dict
    val: any
        Value to add or set
    """

    if len(list_path) == 1:
        key_in = list_path[0]
        dict_in[key_in] = val
        return

    key_next = list_path[0]
    if key_next not in dict_in.keys():
        dict_in[key_next] = {}
    set_dict_item_recursive(dict_in[key_next], list_path[1:], val)


# from rtc_s1.py
def split_runconfig(cfg_in, child_output_dir, burst_product_id_list, child_scratch_path=None, parent_logfile_path=None):
    """
    Split the input runconfig into single burst runconfigs.
    Writes out the burst runconfigs.
    Return the list of the burst runconfigs.

    Parameters
    ----------
    cfg_in: rtc.runconfig.RunConfig
        Path to the original runconfig
    child_output_dir: str
        Output directory of the child process
    burst_product_id_list: list(str)
        List of product IDs
    child_scratch_path: str
        Scratch path to of the child process.
        If `None`, the scratch path of the child processes it will be:
         "[scratch path of parent process]_child_scratch"
    parent_logfile_path: str
        Path to the parent processes' logfile

    Returns
    -------
    runconfig_burst_list: list(str)
        List of the burst runconfigs
    logfile_burst_list: list(str)
        List of the burst logfiles
    """

    with open(cfg_in.run_config_path, encoding='utf8') as fin:
        runconfig_dict_in = yaml.safe_load(fin.read())

    runconfig_burst_list = []
    logfile_burst_list = []

    # determine the bursts to process
    list_burst_id = cfg_in.bursts.keys()

    # determine the scratch path for the child process

    if not child_scratch_path:
        child_scratch_path = os.path.join(
            cfg_in.groups.product_group.scratch_path, f'{os.path.basename(child_output_dir)}_child_scratch'
        )

    if parent_logfile_path:
        # determine the output directory for child process
        basename_logfile = os.path.basename(parent_logfile_path)
    else:
        basename_logfile = None

    for burst_id, burst_product_id in zip(list_burst_id, burst_product_id_list):
        path_temp_runconfig = os.path.join(cfg_in.scratch_path, f'burst_runconfig_{burst_id}.yaml')
        if parent_logfile_path:
            path_logfile_child = os.path.join(child_output_dir, burst_id, basename_logfile)

        else:
            path_logfile_child = None

        runconfig_dict_out = runconfig_dict_in.copy()

        set_dict_item_recursive(
            runconfig_dict_out, ['runconfig', 'groups', 'product_group', 'product_id'], burst_product_id
        )

        set_dict_item_recursive(runconfig_dict_out, ['runconfig', 'groups', 'input_file_group', 'burst_id'], [burst_id])

        set_dict_item_recursive(
            runconfig_dict_out, ['runconfig', 'groups', 'processing', 'geocoding', 'memory_mode'], 'single_block'
        )

        set_dict_item_recursive(
            runconfig_dict_out, ['runconfig', 'groups', 'product_group', 'output_dir'], child_output_dir
        )

        set_dict_item_recursive(
            runconfig_dict_out, ['runconfig', 'groups', 'product_group', 'scratch_path'], child_scratch_path
        )

        set_dict_item_recursive(runconfig_dict_out, ['runconfig', 'groups', 'product_group', 'save_mosaics'], False)

        set_dict_item_recursive(runconfig_dict_out, ['runconfig', 'groups', 'product_group', 'save_bursts'], True)

        runconfig_burst_list.append(path_temp_runconfig)
        logfile_burst_list.append(path_logfile_child)

        with open(path_temp_runconfig, 'w+', encoding='utf8') as fout:
            yaml.dump(runconfig_dict_out, fout)

    return runconfig_burst_list, logfile_burst_list


def compute_correction_lut(
    burst_in,
    dem_raster,
    scratch_path,
    rg_step_meters,
    az_step_meters,
    apply_bistatic_delay_correction,
    apply_static_tropospheric_delay_correction,
):
    """
    Compute lookup table for geolocation correction.
    Applied corrections are: bistatic delay (azimuth),
                             static troposphere delay (range)

    Parameters
    ----------
    burst_in: Sentinel1BurstSlc
        Input burst SLC
    dem_raster: isce3.io.raster
        DEM to run rdr2geo
    scratch_path: str
        Scratch path where the radargrid rasters will be saved
    rg_step_meters: float
        LUT spacing in slant range. Unit: meters
    az_step_meters: float
        LUT spacing in azimth direction. Unit: meters
    apply_bistatic_delay_correction: bool
        Flag to indicate whether the bistatic delay correciton should be applied
    apply_static_tropospheric_delay_correction: bool
        Flag to indicate whether the static tropospheric delay correction should be
        applied

    Returns
    -------
    rg_lut, az_lut: isce3.core.LUT2d
        LUT2d for geolocation correction in slant range and azimuth direction
    """

    rg_lut = None
    az_lut = None

    if not apply_bistatic_delay_correction and not apply_static_tropospheric_delay_correction:
        return rg_lut, az_lut

    # approximate conversion of az_step_meters from meters to seconds
    numrow_orbit = burst_in.orbit.position.shape[0]
    vel_mid = burst_in.orbit.velocity[numrow_orbit // 2, :]
    spd_mid = np.linalg.norm(vel_mid)
    pos_mid = burst_in.orbit.position[numrow_orbit // 2, :]
    alt_mid = np.linalg.norm(pos_mid)

    r = 6371000.0  # geometric mean of WGS84 ellipsoid

    az_step_sec = (az_step_meters * alt_mid) / (spd_mid * r)
    # Bistatic - azimuth direction
    bistatic_delay = burst_in.bistatic_delay(range_step=rg_step_meters, az_step=az_step_sec)

    if apply_bistatic_delay_correction:
        az_lut = isce3.core.LUT2d(
            bistatic_delay.x_start,
            bistatic_delay.y_start,
            bistatic_delay.x_spacing,
            bistatic_delay.y_spacing,
            -bistatic_delay.data,
        )

    if not apply_static_tropospheric_delay_correction:
        return rg_lut, az_lut

    # Calculate rdr2geo rasters
    epsg = dem_raster.get_epsg()
    proj = isce3.core.make_projection(epsg)
    ellipsoid = proj.ellipsoid

    rdr_grid = burst_in.as_isce3_radargrid(az_step=az_step_sec, rg_step=rg_step_meters)

    grid_doppler = isce3.core.LUT2d()

    # Initialize the rdr2geo object
    rdr2geo_obj = isce3.geometry.Rdr2Geo(rdr_grid, burst_in.orbit, ellipsoid, grid_doppler, threshold=1.0e-8)

    # Get the rdr2geo raster needed for SET computation
    topo_output = {
        f'{scratch_path}/height.rdr': gdal.GDT_Float32,
        f'{scratch_path}/incidence_angle.rdr': gdal.GDT_Float32,
    }

    raster_list = []
    for fname, dtype in topo_output.items():
        topo_output_raster = isce3.io.Raster(fname, rdr_grid.width, rdr_grid.length, 1, dtype, 'ENVI')
        raster_list.append(topo_output_raster)

    height_raster, incidence_raster = raster_list

    rdr2geo_obj.topo(
        dem_raster, x_raster=None, y_raster=None, height_raster=height_raster, incidence_angle_raster=incidence_raster
    )

    height_raster.close_dataset()
    incidence_raster.close_dataset()

    # Load height and incidence angle layers
    height_arr = gdal.Open(f'{scratch_path}/height.rdr', gdal.GA_ReadOnly).ReadAsArray()
    incidence_angle_arr = gdal.Open(f'{scratch_path}/incidence_angle.rdr', gdal.GA_ReadOnly).ReadAsArray()

    # static troposphere delay - range direction
    # reference:
    # Breit et al., 2010, TerraSAR-X SAR Processing and Products,
    # IEEE Transactions on Geoscience and Remote Sensing, 48(2), 727-740.
    # DOI: 10.1109/TGRS.2009.2035497
    zenith_path_delay = 2.3
    reference_height = 6000.0
    tropo = zenith_path_delay / np.cos(np.deg2rad(incidence_angle_arr)) * np.exp(-1 * height_arr / reference_height)

    # Prepare the computation results into LUT2d
    rg_lut = isce3.core.LUT2d(
        bistatic_delay.x_start, bistatic_delay.y_start, bistatic_delay.x_spacing, bistatic_delay.y_spacing, tropo
    )

    return rg_lut, az_lut


def _create_raster_obj(
    output_dir,
    product_id,
    layer_name,
    dtype,
    shape,
    radar_grid_file_dict,
    output_obj_list,
    flag_create_raster_obj,
    extension,
):
    """Create an ISCE3 raster object (GTiff) for a radar geometry layer.

    Parameters
    ----------
    output_dir: str
           Output directory
    layer_name: str
           Layer name
    product_id: str
           Product ID
    ds_hdf5: str
           HDF5 dataset name
    dtype:: gdal.DataType
           GDAL data type
    shape: list
           Shape of the output raster
    radar_grid_file_dict: dict
           Dictionary that will hold the name of the output file
           referenced by the contents of `ds_hdf5` (dict key)
    output_obj_list: list
           Mutable list of output raster objects
    flag_create_raster_obj: bool
           Flag indicating if raster object should be created

    Returns
    -------
    raster_obj : isce3.io.Raster
           ISCE3 raster object
    """
    if flag_create_raster_obj is not True:
        return None

    ds_name = f'{product_id}_{layer_name}'

    output_file = os.path.join(output_dir, ds_name) + '.' + extension
    raster_obj = isce3.io.Raster(output_file, shape[2], shape[1], shape[0], dtype, 'GTiff')
    output_obj_list.append(raster_obj)
    radar_grid_file_dict[layer_name] = output_file
    return raster_obj


def apply_slc_corrections(
    burst_in: Sentinel1BurstSlc,
    path_slc_vrt: str,
    path_slc_out: str,
    flag_output_complex: bool = False,
    flag_thermal_correction: bool = True,
    flag_apply_abs_rad_correction: bool = True,
):
    """Apply thermal correction stored in burst_in. Save the corrected signal
    back to ENVI format. Preserves the phase when the output is complex

    Parameters
    ----------
    burst_in: Sentinel1BurstSlc
        Input burst to apply the correction
    path_slc_vrt: str
        Path to the input burst to apply correction
    path_slc_out: str
        Path to the output SLC which the corrections are applied
    flag_output_complex: bool
        `path_slc_out` will be in complex number when this is `True`
        Otherwise, the output will be amplitude only.
    flag_thermal_correction: bool
        flag whether or not to apple the thermal correction.
    flag_apply_abs_rad_correction: bool
        Flag to apply radiometric calibration
    """

    # Load the SLC of the burst
    burst_in.slc_to_vrt_file(path_slc_vrt)
    slc_gdal_ds = gdal.Open(path_slc_vrt)
    arr_slc_from = slc_gdal_ds.ReadAsArray()

    # Apply thermal noise correction
    if flag_thermal_correction:
        logger.info('    applying thermal noise correction to burst SLC')
        corrected_image = np.abs(arr_slc_from) ** 2 - burst_in.thermal_noise_lut
        min_backscatter = 0
        max_backscatter = None
        corrected_image = np.clip(corrected_image, min_backscatter, max_backscatter)
    else:
        corrected_image = np.abs(arr_slc_from) ** 2

    # Apply absolute radiometric correction
    if flag_apply_abs_rad_correction:
        logger.info('    applying absolute radiometric correction to burst SLC')
        corrected_image = corrected_image / burst_in.burst_calibration.beta_naught**2

    # Output as complex
    if flag_output_complex:
        factor_mag = np.sqrt(corrected_image) / np.abs(arr_slc_from)
        factor_mag[np.isnan(factor_mag)] = 0.0
        corrected_image = arr_slc_from * factor_mag
        dtype = gdal.GDT_CFloat32
    else:
        dtype = gdal.GDT_Float32

    # Save the corrected image
    drvout = gdal.GetDriverByName('GTiff')
    raster_out = drvout.Create(path_slc_out, burst_in.shape[1], burst_in.shape[0], 1, dtype)
    band_out = raster_out.GetRasterBand(1)
    band_out.WriteArray(corrected_image)
    band_out.FlushCache()
    del band_out


def _test_valid_gdal_ref(gdal_ref):
    """
    Test if the input string contains a valid GDAL reference.

    Parameters
    -----------
    gdal_ref: str
        Input string

    Returns
    -------
    _ : bool
        Boolean value indicating if the input string is a valid GDAL reference
    """
    try:
        gdal_ds = gdal.Open(gdal_ref, gdal.GA_ReadOnly)
    except:  # noqa
        return False
    return gdal_ds is not None


def set_mask_fill_value_and_ctable(mask_file, reference_file):
    """
    Update color table and fill values of the layover shadow mask using
    another file as reference for invalid samples

    Parameters
    -----------
    mask_file: str
        Layover/shadow mask file
    reference_file: str
        File to be used as reference for invalid samples

    """
    logger.info('    updating layover/shadow mask with fill value and color table')
    ref_gdal_ds = gdal.Open(reference_file, gdal.GA_ReadOnly)
    ref_gdal_band = ref_gdal_ds.GetRasterBand(1)
    ref_array = ref_gdal_band.ReadAsArray()

    mask_gdal_ds = gdal.Open(mask_file, gdal.GA_Update)
    mask_ctable = gdal.ColorTable()

    # Light gray - Not masked
    mask_ctable.SetColorEntry(0, (175, 175, 175))

    # Shadow - Dark gray
    mask_ctable.SetColorEntry(1, (64, 64, 64))

    # White - Layover
    mask_ctable.SetColorEntry(2, (255, 255, 255))

    # Cyan - Layover and shadow
    mask_ctable.SetColorEntry(3, (0, 255, 255))

    # No data
    mask_gdal_band = mask_gdal_ds.GetRasterBand(1)
    mask_array = mask_gdal_band.ReadAsArray()
    mask_array[(np.isnan(ref_array)) & (mask_array == 0)] = 255
    mask_gdal_band.SetNoDataValue(255)

    mask_ctable.SetColorEntry(255, (0, 0, 0, 0))
    mask_gdal_band.SetRasterColorTable(mask_ctable)
    mask_gdal_band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
    mask_gdal_band.WriteArray(mask_array)

    del mask_gdal_band
    del mask_gdal_ds


def compute_layover_shadow_mask(
    radar_grid: isce3.product.RadarGridParameters,
    orbit: isce3.core.Orbit,
    geogrid_in: isce3.product.GeoGridParameters,
    burst_in: Sentinel1BurstSlc,
    dem_raster: isce3.io.Raster,
    filename_out: str,
    output_raster_format: str,
    scratch_dir: str,
    shadow_dilation_size: int,
    threshold_rdr2geo: float = 1.0e-7,
    numiter_rdr2geo: int = 25,
    extraiter_rdr2geo: int = 10,
    lines_per_block_rdr2geo: int = 1000,
    threshold_geo2rdr: float = 1.0e-7,
    numiter_geo2rdr: int = 25,
    memory_mode: isce3.core.GeocodeMemoryMode = None,
    geocode_options=None,
):
    """
    Compute the layover/shadow mask and geocode it

    Parameters
    -----------
    radar_grid: isce3.product.RadarGridParameters
        Radar grid
    orbit: isce3.core.Orbit
        Orbit defining radar motion on input path
    geogrid_in: isce3.product.GeoGridParameters
        Geogrid to geocode the layover/shadow mask in radar grid
    burst_in: Sentinel1BurstSlc
        Input burst
    geogrid_in: isce3.product.GeoGridParameters
        Geogrid to geocode the layover/shadow mask in radar grid
    dem_raster: isce3.io.Raster
        DEM raster
    filename_out: str
        Path to the geocoded layover/shadow mask
    output_raster_format: str
        File format of the layover/shadow mask
    scratch_dir: str
        Temporary Directory
    shadow_dilation_size: int
        Layover/shadow mask dilation size of shadow pixels
    threshold_rdr2geo: float
        Iteration threshold for rdr2geo
    numiter_rdr2geo: int
        Number of max. iteration for rdr2geo object
    extraiter_rdr2geo: int
        Extra number of iteration for rdr2geo object
    lines_per_block_rdr2geo: int
        Lines per block for rdr2geo
    threshold_geo2rdr: float
        Iteration threshold for geo2rdr
    numiter_geo2rdr: int
        Number of max. iteration for geo2rdr object
    memory_mode: isce3.core.GeocodeMemoryMode
        Geocoding memory mode
    geocode_options: dict
        Keyword arguments to be passed to the geocode() function
        when map projection the layover/shadow mask

    Returns
    -------
    slantrange_layover_shadow_mask_raster: isce3.io.Raster
        Layover/shadow-mask ISCE3 raster object in radar coordinates
    """

    # determine the output filename
    str_datetime = burst_in.sensing_start.strftime('%Y%m%d_%H%M%S.%f')

    # Run topo to get layover/shadow mask
    ellipsoid = isce3.core.Ellipsoid()

    Rdr2Geo = isce3.geometry.Rdr2Geo

    grid_doppler = isce3.core.LUT2d()

    rdr2geo_obj = Rdr2Geo(
        radar_grid,
        orbit,
        ellipsoid,
        grid_doppler,
        threshold=threshold_rdr2geo,
        numiter=numiter_rdr2geo,
        extraiter=extraiter_rdr2geo,
        lines_per_block=lines_per_block_rdr2geo,
    )

    if shadow_dilation_size > 0:
        path_layover_shadow_mask_file = os.path.join(scratch_dir, 'layover_shadow_mask_slant_range.tif')
        slantrange_layover_shadow_mask_raster = isce3.io.Raster(
            path_layover_shadow_mask_file, radar_grid.width, radar_grid.length, 1, gdal.GDT_Byte, 'GTiff'
        )
    else:
        path_layover_shadow_mask = f'layover_shadow_mask_{burst_in.burst_id}_{burst_in.polarization}_{str_datetime}'
        slantrange_layover_shadow_mask_raster = isce3.io.Raster(
            path_layover_shadow_mask, radar_grid.width, radar_grid.length, 1, gdal.GDT_Byte, 'MEM'
        )

    rdr2geo_obj.topo(dem_raster, layover_shadow_raster=slantrange_layover_shadow_mask_raster)

    if shadow_dilation_size > 1:
        """
        constants from ISCE3:
            SHADOW_VALUE = 1;
            LAYOVER_VALUE = 2;
            LAYOVER_AND_SHADOW_VALUE = 3;
        We only want to dilate values 1 and 3
        """

        # flush raster data to the disk
        slantrange_layover_shadow_mask_raster.close_dataset()
        del slantrange_layover_shadow_mask_raster

        # read layover/shadow mask
        gdal_ds = gdal.Open(path_layover_shadow_mask_file, gdal.GA_Update)
        gdal_band = gdal_ds.GetRasterBand(1)
        slantrange_layover_shadow_mask = gdal_band.ReadAsArray()

        # save layover pixels and substitute them with 0
        ind = np.where(slantrange_layover_shadow_mask == 2)
        slantrange_layover_shadow_mask[ind] = 0

        # perform grey dilation
        slantrange_layover_shadow_mask = ndimage.grey_dilation(
            slantrange_layover_shadow_mask, size=(shadow_dilation_size, shadow_dilation_size)
        )

        # restore layover pixels
        slantrange_layover_shadow_mask[ind] = 2

        # write dilated layover/shadow mask
        gdal_band.WriteArray(slantrange_layover_shadow_mask)

        # flush updates to the disk
        gdal_band.FlushCache()
        gdal_band = None
        gdal_ds = None

        slantrange_layover_shadow_mask_raster = isce3.io.Raster(path_layover_shadow_mask_file)

    # geocode the layover/shadow mask
    geo = isce3.geocode.GeocodeFloat32()
    geo.orbit = orbit
    geo.ellipsoid = ellipsoid
    geo.doppler = isce3.core.LUT2d()
    geo.threshold_geo2rdr = threshold_geo2rdr
    geo.numiter_geo2rdr = numiter_geo2rdr
    geo.data_interpolator = 'NEAREST'
    geo.geogrid(
        float(geogrid_in.start_x),
        float(geogrid_in.start_y),
        float(geogrid_in.spacing_x),
        float(geogrid_in.spacing_y),
        int(geogrid_in.width),
        int(geogrid_in.length),
        int(geogrid_in.epsg),
    )

    geocoded_layover_shadow_mask_raster = isce3.io.Raster(
        filename_out, geogrid_in.width, geogrid_in.length, 1, gdal.GDT_Byte, output_raster_format
    )

    if geocode_options is None:
        geocode_options = {}

    if memory_mode is not None:
        geocode_options['memory_mode'] = memory_mode

    geo.geocode(
        radar_grid=radar_grid,
        input_raster=slantrange_layover_shadow_mask_raster,
        output_raster=geocoded_layover_shadow_mask_raster,
        dem_raster=dem_raster,
        output_mode=isce3.geocode.GeocodeOutputMode.INTERP,
        **geocode_options,
    )

    # flush data to the disk
    geocoded_layover_shadow_mask_raster.close_dataset()
    del geocoded_layover_shadow_mask_raster

    return slantrange_layover_shadow_mask_raster


def read_and_validate_rtc_anf_flags(geocode_namespace, flag_apply_rtc, output_terrain_radiometry, logger):
    """
    Read and validate radiometric terrain correction (RTC) area
    normalization factor (ANF) flags

    Parameters
    ----------
    geocode_namespace: types.SimpleNamespace
        Runconfig geocode namespace
    flag_apply_rtc: Bool
        Flag apply RTC (radiometric terrain correction)
    output_terrain_radiometry: isce3.geometry.RtcOutputTerrainRadiometry
        Output terrain radiometry (backscatter coefficient convention)
    logger : loggin.Logger
        Logger

    Returns
    -------
    save_rtc_anf: bool
        Flag indicating wheter the radiometric terrain correction (RTC)
        area normalization factor (ANF) layer should be created
    save_rtc_anf_gamma0_to_sigma0: bool
        Flag indicating wheter the radiometric terrain correction (RTC)
        area normalization factor (ANF) gamma0 to sigma0 layer should be
        created
    """
    save_rtc_anf = geocode_namespace.save_rtc_anf
    save_rtc_anf_gamma0_to_sigma0 = geocode_namespace.save_rtc_anf_gamma0_to_sigma0

    if not flag_apply_rtc and save_rtc_anf:
        logger.warning(
            'WARNING the option `save_rtc_anf` is not available'
            ' with radiometric terrain correction'
            ' disabled (`apply_rtc = False`). Setting'
            ' flag `save_rtc_anf` to `False`.'
        )
        save_rtc_anf = False

    if not flag_apply_rtc and save_rtc_anf_gamma0_to_sigma0:
        logger.warning = (
            'WARNING the option `save_rtc_anf_gamma0_to_sigma0`'
            ' is not available with radiometric terrain'
            ' correction disabled (`apply_rtc = False`).'
            ' Setting flag `save_rtc_anf_gamma0_to_sigma0` to'
            ' `False`.'
        )
        save_rtc_anf_gamma0_to_sigma0 = False
    elif (
        save_rtc_anf_gamma0_to_sigma0
        and output_terrain_radiometry == isce3.geometry.RtcOutputTerrainRadiometry.SIGMA_NAUGHT
    ):
        logger.warning = (
            'WARNING the option `save_rtc_anf_gamma0_to_sigma0`'
            ' is not available with output radiometric terrain'
            ' radiometry (`output_type`) set to `sigma0`.'
            ' Setting flag `save_rtc_anf_gamma0_to_sigma0` to'
            ' `False`.'
        )
        save_rtc_anf_gamma0_to_sigma0 = False

    return save_rtc_anf, save_rtc_anf_gamma0_to_sigma0


def get_radar_grid(
    geogrid,
    dem_interp_method_enum,
    product_id,
    output_dir,
    extension,
    save_local_inc_angle,
    save_incidence_angle,
    save_projection_angle,
    save_rtc_anf_projection_angle,
    save_range_slope,
    save_dem,
    dem_raster,
    radar_grid_file_dict,
    lookside,
    wavelength,
    orbit,
    verbose=True,
):
    output_obj_list = []
    layers_nbands = 1
    shape = [layers_nbands, geogrid.length, geogrid.width]

    local_incidence_angle_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_LOCAL_INCIDENCE_ANGLE,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_local_inc_angle,
        extension,
    )
    incidence_angle_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_INCIDENCE_ANGLE,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_incidence_angle,
        extension,
    )
    projection_angle_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_PROJECTION_ANGLE,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_projection_angle,
        extension,
    )
    rtc_anf_projection_angle_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_RTC_ANF_PROJECTION_ANGLE,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_rtc_anf_projection_angle,
        extension,
    )
    range_slope_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_RANGE_SLOPE,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_range_slope,
        extension,
    )
    interpolated_dem_raster = _create_raster_obj(
        output_dir,
        product_id,
        LAYER_NAME_DEM,
        gdal.GDT_Float32,
        shape,
        radar_grid_file_dict,
        output_obj_list,
        save_dem,
        extension,
    )

    # TODO review this (Doppler)!!!
    # native_doppler = burst.doppler.lut2d
    native_doppler = isce3.core.LUT2d()
    native_doppler.bounds_error = False
    grid_doppler = isce3.core.LUT2d()
    grid_doppler.bounds_error = False

    # TODO: update code below
    # Computation of range slope is not merged to ISCE yet
    kwargs_get_radar_grid = {}
    if range_slope_raster:
        kwargs_get_radar_grid['range_slope_angle_raster'] = range_slope_raster

    # call get_radar_grid()
    isce3.geogrid.get_radar_grid(
        lookside,
        wavelength,
        dem_raster,
        geogrid,
        orbit,
        native_doppler,
        grid_doppler,
        incidence_angle_raster=incidence_angle_raster,
        local_incidence_angle_raster=local_incidence_angle_raster,
        projection_angle_raster=projection_angle_raster,
        simulated_radar_brightness_raster=rtc_anf_projection_angle_raster,
        interpolated_dem_raster=interpolated_dem_raster,
        dem_interp_method=dem_interp_method_enum,
        **kwargs_get_radar_grid,
    )

    # Flush data
    for obj in output_obj_list:
        del obj

    if not verbose:
        return


@dataclass
class RtcOptions:
    output_dir: str
    scratch_dir: str
    rtc: bool = True
    thermal_noise: bool = True
    abs_rad: bool = True
    bistatic_delay: bool = True
    static_tropo: bool = True
    save_metadata: bool = True


def run_single_job(burst: Sentinel1BurstSlc, cfg: RunConfig, opts: RtcOptions):
    """
    Run geocode burst workflow with user-defined
    args stored in dictionary runconfig `cfg`

    Parameters
    ---------
    cfg: RunConfig
        RunConfig object with user runconfig options
    """
    t_start = time.time()
    raster_format = 'GTiff'
    raster_extension = 'tif'

    # unpack processing parameters
    dem_interp_method_enum = cfg.groups.processing.dem_interpolation_method_enum

    # unpack geocode run parameters
    geocode_namespace = cfg.groups.processing.geocoding
    apply_valid_samples_sub_swath_masking = cfg.groups.processing.geocoding.apply_valid_samples_sub_swath_masking
    apply_shadow_masking = cfg.groups.processing.geocoding.apply_shadow_masking
    if cfg.groups.processing.geocoding.algorithm_type == 'area_projection':
        geocode_algorithm = isce3.geocode.GeocodeOutputMode.AREA_PROJECTION
    else:
        geocode_algorithm = isce3.geocode.GeocodeOutputMode.INTERP
    az_step_meters = cfg.groups.processing.correction_lut_azimuth_spacing_in_meters
    rg_step_meters = cfg.groups.processing.correction_lut_range_spacing_in_meters
    memory_mode = geocode_namespace.memory_mode
    geogrid_upsampling = geocode_namespace.geogrid_upsampling
    shadow_dilation_size = geocode_namespace.shadow_dilation_size
    abs_cal_factor = geocode_namespace.abs_rad_cal
    clip_max = geocode_namespace.clip_max
    clip_min = geocode_namespace.clip_min
    flag_upsample_radar_grid = geocode_namespace.upsample_radargrid
    save_nlooks = geocode_namespace.save_nlooks
    save_mask = geocode_namespace.save_mask

    # unpack RTC run parameters
    rtc_namespace = cfg.groups.processing.rtc
    if rtc_namespace.algorithm_type == 'bilinear_distribution':
        rtc_algorithm = isce3.geometry.RtcAlgorithm.RTC_BILINEAR_DISTRIBUTION
    else:
        rtc_algorithm = isce3.geometry.RtcAlgorithm.RTC_AREA_PROJECTION
    input_terrain_radiometry = rtc_namespace.input_terrain_radiometry
    input_terrain_radiometry_enum = rtc_namespace.input_terrain_radiometry_enum
    output_terrain_radiometry = rtc_namespace.output_type
    output_terrain_radiometry_enum = rtc_namespace.output_type_enum
    if opts.rtc:
        layer_name_rtc_anf = f'rtc_anf_{output_terrain_radiometry}_to_{input_terrain_radiometry}'
    else:
        layer_name_rtc_anf = ''

    save_rtc_anf, save_rtc_anf_gamma0_to_sigma0 = read_and_validate_rtc_anf_flags(
        geocode_namespace, opts.rtc, output_terrain_radiometry_enum, logger
    )
    rtc_min_value_db = rtc_namespace.rtc_min_value_db
    rtc_upsampling = rtc_namespace.dem_upsampling
    rtc_area_beta_mode = rtc_namespace.area_beta_mode
    if rtc_area_beta_mode == 'pixel_area':
        rtc_area_beta_mode_enum = isce3.geometry.RtcAreaBetaMode.PIXEL_AREA
    elif rtc_area_beta_mode == 'projection_angle':
        rtc_area_beta_mode_enum = isce3.geometry.RtcAreaBetaMode.PROJECTION_ANGLE
    elif rtc_area_beta_mode == 'auto' or rtc_area_beta_mode is None:
        rtc_area_beta_mode_enum = isce3.geometry.RtcAreaBetaMode.AUTO
    else:
        err_msg = f'ERROR invalid area beta mode: {rtc_area_beta_mode}'
        raise ValueError(err_msg)

    # Common initializations
    dem_raster = isce3.io.Raster(cfg.dem)
    ellipsoid = isce3.core.Ellipsoid()
    zero_doppler = isce3.core.LUT2d()
    threshold = cfg.geo2rdr_params.threshold
    maxiter = cfg.geo2rdr_params.numiter
    exponent = 1 if (opts.thermal_noise or opts.ads_rad) else 2

    tmp_files_list = []
    os.makedirs(opts.output_dir, exist_ok=True)
    os.makedirs(opts.scratch_dir, exist_ok=True)
    vrt_options_mosaic = gdal.BuildVRTOptions(separate=True)

    lookside = None
    wavelength = None
    orbit = None

    # iterate over sub-burts
    burst_id = str(burst.burst_id)
    t_burst_start = time.time()

    burst_output_file_list = []

    geogrid = cfg.geogrids[burst_id]
    pol = burst.polarization
    pol_list = [pol]
    burst_product_id = 'burst1'

    burst_scratch_path = f'{opts.scratch_dir}/{burst_id}/'
    os.makedirs(burst_scratch_path, exist_ok=True)

    output_dir_bursts = os.path.join(opts.output_dir, burst_id)
    os.makedirs(output_dir_bursts, exist_ok=True)
    output_dir_sec_bursts = output_dir_bursts

    logger.info('    burst geogrid:')
    for line in str(geogrid).split('\n'):
        if not line:
            continue
        logger.info(f'        {line}')

    # snap coordinates
    x_snap = geogrid.spacing_x
    y_snap = geogrid.spacing_y
    geogrid.start_x = snap_coord(geogrid.start_x, x_snap, np.floor)
    geogrid.start_y = snap_coord(geogrid.start_y, y_snap, np.ceil)

    # Create burst HDF5
    if opts.save_metadata:
        hdf5_file_output_dir = os.path.join(opts.output_dir, burst_id)
        os.makedirs(hdf5_file_output_dir, exist_ok=True)

    # If burst imagery is not temporary, separate polarization channels
    output_burst_imagery_list = []
    for pol in pol_list:
        geo_burst_pol_filename = os.path.join(output_dir_bursts, f'{burst_product_id}_{pol}.{raster_extension}')
        output_burst_imagery_list.append(geo_burst_pol_filename)

    logger.info('    reading burst SLCs')

    radar_grid = burst.as_isce3_radargrid()
    orbit = burst.orbit
    wavelength = burst.wavelength
    lookside = radar_grid.lookside

    input_file_list = []
    temp_slc_path = os.path.join(burst_scratch_path, f'slc_{pol}.vrt')
    temp_slc_corrected_path = os.path.join(burst_scratch_path, f'slc_{pol}_corrected.{raster_extension}')
    if opts.thermal_noise or opts.abs_rad:
        apply_slc_corrections(
            burst,
            temp_slc_path,
            temp_slc_corrected_path,
            flag_output_complex=False,
            flag_thermal_correction=opts.thermal_noise,
            flag_apply_abs_rad_correction=True,
        )
        input_burst_filename = temp_slc_corrected_path
        tmp_files_list.append(temp_slc_corrected_path)
    else:
        input_burst_filename = temp_slc_path

    tmp_files_list.append(temp_slc_path)
    input_file_list.append(input_burst_filename)

    # At this point, burst imagery files are always temporary
    geo_burst_filename = f'{burst_scratch_path}/{burst_product_id}.{raster_extension}'
    tmp_files_list.append(geo_burst_filename)

    out_geo_nlooks_obj = None
    if save_nlooks:
        nlooks_file = f'{output_dir_sec_bursts}/{burst_product_id}_{LAYER_NAME_NUMBER_OF_LOOKS}.{raster_extension}'
        burst_output_file_list.append(nlooks_file)
    else:
        nlooks_file = None

    out_geo_rtc_obj = None
    if save_rtc_anf:
        rtc_anf_file = f'{output_dir_sec_bursts}/{burst_product_id}_{layer_name_rtc_anf}.{raster_extension}'
        burst_output_file_list.append(rtc_anf_file)
    else:
        rtc_anf_file = None

    out_geo_rtc_gamma0_to_sigma0_obj = None
    if save_rtc_anf_gamma0_to_sigma0:
        rtc_anf_gamma0_to_sigma0_file = (
            f'{output_dir_sec_bursts}/{burst_product_id}_{LAYER_NAME_RTC_ANF_GAMMA0_TO_SIGMA0}.{raster_extension}'
        )
        burst_output_file_list.append(rtc_anf_gamma0_to_sigma0_file)
    else:
        rtc_anf_gamma0_to_sigma0_file = None

    # geocoding optional arguments
    geocode_kwargs = {}
    layover_shadow_mask_geocode_kwargs = {}

    # get sub_swaths metadata
    if apply_valid_samples_sub_swath_masking:
        # Extract burst boundaries and create sub_swaths object to mask
        # invalid radar samples
        n_subswaths = 1
        sub_swaths = isce3.product.SubSwaths(radar_grid.length, radar_grid.width, n_subswaths)
        last_range_sample = min([burst.last_valid_sample, radar_grid.width])
        valid_samples_sub_swath = np.repeat(
            [[burst.first_valid_sample, last_range_sample + 1]], radar_grid.length, axis=0
        )
        for i in range(burst.first_valid_line):
            valid_samples_sub_swath[i, :] = 0
        for i in range(burst.last_valid_line, radar_grid.length):
            valid_samples_sub_swath[i, :] = 0

        sub_swaths.set_valid_samples_array(1, valid_samples_sub_swath)
        geocode_kwargs['sub_swaths'] = sub_swaths
        layover_shadow_mask_geocode_kwargs['sub_swaths'] = sub_swaths

    # Calculate geolocation correction LUT
    if opts.bistatic_delay or opts.static_tropo:
        # Calculates the LUTs for one polarization in `burst_pol_dict`
        rg_lut, az_lut = compute_correction_lut(
            burst,
            dem_raster,
            burst_scratch_path,
            rg_step_meters,
            az_step_meters,
            opts.bistatic_delay,
            opts.static_tropo,
        )

        if az_lut is not None:
            geocode_kwargs['az_time_correction'] = az_lut

        if rg_lut is not None:
            geocode_kwargs['slant_range_correction'] = rg_lut

    # Calculate layover/shadow mask when requested
    if save_mask or apply_shadow_masking:
        flag_layover_shadow_mask_is_temporary = apply_shadow_masking and not save_mask
        if flag_layover_shadow_mask_is_temporary:
            # layover/shadow mask is temporary
            layover_shadow_mask_file = (
                f'{burst_scratch_path}/{burst_product_id}_{LAYER_NAME_LAYOVER_SHADOW_MASK}.{raster_extension}'
            )
        else:
            # layover/shadow mask is saved in `output_dir_sec_bursts`
            layover_shadow_mask_file = (
                f'{output_dir_sec_bursts}/{burst_product_id}_{LAYER_NAME_LAYOVER_SHADOW_MASK}.{raster_extension}'
            )
        logger.info(f'    computing layover shadow mask for {burst_id}')
        radar_grid_layover_shadow_mask = radar_grid
        slantrange_layover_shadow_mask_raster = compute_layover_shadow_mask(
            radar_grid_layover_shadow_mask,
            orbit,
            geogrid,
            burst,
            dem_raster,
            layover_shadow_mask_file,
            raster_format,
            burst_scratch_path,
            shadow_dilation_size=shadow_dilation_size,
            threshold_rdr2geo=cfg.rdr2geo_params.threshold,
            numiter_rdr2geo=cfg.rdr2geo_params.numiter,
            threshold_geo2rdr=cfg.geo2rdr_params.threshold,
            numiter_geo2rdr=cfg.geo2rdr_params.numiter,
            memory_mode=geocode_namespace.memory_mode,
            geocode_options=layover_shadow_mask_geocode_kwargs,
        )

        if flag_layover_shadow_mask_is_temporary:
            tmp_files_list.append(layover_shadow_mask_file)
        else:
            burst_output_file_list.append(layover_shadow_mask_file)
            logger.info(f'file saved: {layover_shadow_mask_file}')

        if not save_mask:
            layover_shadow_mask_file = None

        # The radar grid for static layers is multilooked by a factor of
        # STATIC_LAYERS_LAYOVER_SHADOW_MASK_MULTILOOK_FACTOR. If that
        # number is not unitary, the layover shadow mask cannot be used
        # with geocoding
        if apply_shadow_masking or STATIC_LAYERS_LAYOVER_SHADOW_MASK_MULTILOOK_FACTOR == 1:
            geocode_kwargs['input_layover_shadow_mask_raster'] = slantrange_layover_shadow_mask_raster
    else:
        layover_shadow_mask_file = None

    if save_nlooks:
        out_geo_nlooks_obj = isce3.io.Raster(
            nlooks_file, geogrid.width, geogrid.length, 1, gdal.GDT_Float32, raster_format
        )

    if save_rtc_anf:
        out_geo_rtc_obj = isce3.io.Raster(
            rtc_anf_file, geogrid.width, geogrid.length, 1, gdal.GDT_Float32, raster_format
        )

    if save_rtc_anf_gamma0_to_sigma0:
        out_geo_rtc_gamma0_to_sigma0_obj = isce3.io.Raster(
            rtc_anf_gamma0_to_sigma0_file,
            geogrid.width,
            geogrid.length,
            1,
            gdal.GDT_Float32,
            raster_format,
        )
        geocode_kwargs['out_geo_rtc_gamma0_to_sigma0'] = out_geo_rtc_gamma0_to_sigma0_obj

    # create multi-band VRT
    if len(input_file_list) == 1:
        rdr_burst_raster = isce3.io.Raster(input_file_list[0])
    else:
        temp_vrt_path = f'{burst_scratch_path}/slc.vrt'
        gdal.BuildVRT(temp_vrt_path, input_file_list, options=vrt_options_mosaic)
        rdr_burst_raster = isce3.io.Raster(temp_vrt_path)
        tmp_files_list.append(temp_vrt_path)

    # Generate output geocoded burst raster
    geo_burst_raster = isce3.io.Raster(
        geo_burst_filename,
        geogrid.width,
        geogrid.length,
        rdr_burst_raster.num_bands,
        gdal.GDT_Float32,
        raster_format,
    )

    # init Geocode object depending on raster type
    if rdr_burst_raster.datatype() == gdal.GDT_Float32:
        geo_obj = isce3.geocode.GeocodeFloat32()
    elif rdr_burst_raster.datatype() == gdal.GDT_Float64:
        geo_obj = isce3.geocode.GeocodeFloat64()
    elif rdr_burst_raster.datatype() == gdal.GDT_CFloat32:
        geo_obj = isce3.geocode.GeocodeCFloat32()
    elif rdr_burst_raster.datatype() == gdal.GDT_CFloat64:
        geo_obj = isce3.geocode.GeocodeCFloat64()
    else:
        err_str = 'Unsupported raster type for geocoding'
        raise NotImplementedError(err_str)

    # init geocode members
    geo_obj.orbit = orbit
    geo_obj.ellipsoid = ellipsoid
    geo_obj.doppler = zero_doppler
    geo_obj.threshold_geo2rdr = threshold
    geo_obj.numiter_geo2rdr = maxiter

    # set data interpolator based on the geocode algorithm
    if geocode_algorithm == isce3.geocode.GeocodeOutputMode.INTERP:
        geo_obj.data_interpolator = geocode_algorithm

    geo_obj.geogrid(
        geogrid.start_x,
        geogrid.start_y,
        geogrid.spacing_x,
        geogrid.spacing_y,
        geogrid.width,
        geogrid.length,
        geogrid.epsg,
    )

    geo_obj.geocode(
        radar_grid=radar_grid,
        input_raster=rdr_burst_raster,
        output_raster=geo_burst_raster,
        dem_raster=dem_raster,
        output_mode=geocode_algorithm,
        geogrid_upsampling=geogrid_upsampling,
        flag_apply_rtc=opts.rtc,
        input_terrain_radiometry=input_terrain_radiometry_enum,
        output_terrain_radiometry=output_terrain_radiometry_enum,
        exponent=exponent,
        rtc_min_value_db=rtc_min_value_db,
        rtc_upsampling=rtc_upsampling,
        rtc_algorithm=rtc_algorithm,
        abs_cal_factor=abs_cal_factor,
        flag_upsample_radar_grid=flag_upsample_radar_grid,
        clip_min=clip_min,
        clip_max=clip_max,
        out_geo_nlooks=out_geo_nlooks_obj,
        out_geo_rtc=out_geo_rtc_obj,
        rtc_area_beta_mode=rtc_area_beta_mode_enum,
        # out_geo_rtc_gamma0_to_sigma0=out_geo_rtc_gamma0_to_sigma0_obj,
        input_rtc=None,
        output_rtc=None,
        dem_interp_method=dem_interp_method_enum,
        memory_mode=memory_mode,
        **geocode_kwargs,
    )

    del geo_burst_raster

    # Output imagery list contains multi-band files that will be used for mosaicking
    if save_mask:
        set_mask_fill_value_and_ctable(layover_shadow_mask_file, geo_burst_filename)

    burst_output_file_list += output_burst_imagery_list

    if save_nlooks:
        out_geo_nlooks_obj.close_dataset()
        del out_geo_nlooks_obj

    if save_rtc_anf:
        out_geo_rtc_obj.close_dataset()
        del out_geo_rtc_obj

    if save_rtc_anf_gamma0_to_sigma0:
        out_geo_rtc_gamma0_to_sigma0_obj.close_dataset()
        del out_geo_rtc_gamma0_to_sigma0_obj

    radar_grid_file_dict = {}
    get_radar_grid(
        geogrid,
        dem_interp_method_enum,
        burst_product_id,
        output_dir_sec_bursts,
        raster_extension,
        False,
        False,
        False,
        False,
        False,
        False,
        dem_raster,
        radar_grid_file_dict,
        lookside,
        wavelength,
        orbit,
        verbose=False,
    )
    radar_grid_file_dict_filenames = list(radar_grid_file_dict.values())
    burst_output_file_list += radar_grid_file_dict_filenames

    t_burst_end = time.time()
    logger.info(f'elapsed time (burst): {t_burst_end - t_burst_start}')

    # end burst processing
    # ===========================================================

    for filename in tmp_files_list:
        if not os.path.isfile(filename):
            continue
        os.remove(filename)

    t_end = time.time()
    logger.info(f'elapsed time: {t_end - t_start}')
