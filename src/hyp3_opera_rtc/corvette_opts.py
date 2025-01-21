from dataclasses import dataclass

import numpy as np


@dataclass
class RtcOptions:
    output_dir: str
    scratch_dir: str
    dem_path: str
    rtc: bool = True
    thermal_noise: bool = True
    abs_rad: bool = True
    bistatic_delay: bool = True
    static_tropo: bool = True
    save_metadata: bool = True
    dem_interpolation_method: str = 'biquintic'
    apply_valid_samples_sub_swath_masking: bool = True
    apply_shadow_masking: bool = True
    geocode_algorithm: str = 'area_projection'  # 'area_projection' or 'interp'
    correction_lut_azimuth_spacing_in_meters: int = 120
    correction_lut_range_spacing_in_meters: int = 120
    memory_mode: str = 'single_block'
    geogrid_upsampling: int = 1
    shadow_dilation_size: int = 0
    abs_cal_factor: int = 1
    clip_min: float = np.nan
    clip_max: float = np.nan
    upsample_radar_grid: bool = False
    save_nlooks: bool = False
    save_mask: bool = True
    save_rtc_anf: bool = False
    save_rtc_anf_gamma0_to_sigma0: bool = False
    terrain_radiometry: str = 'gamma0'  # 'gamma0' or 'sigma0'
    rtc_algorithm_type: str = 'area_projection'  # 'area_projection' or 'bilinear_distribution'
    input_terrain_radiometry: str = 'beta0'
    rtc_min_value_db: int = -30.0
    rtc_upsampling: int = 2
    rtc_area_beta_mode: str = 'auto'
    geo2rdr_threshold: float = 1.0e-7
    geo2rdr_numiter: int = 50
    rdr2geo_threshold: float = 1.0e-7
    rdr2geo_numiter: int = 25
