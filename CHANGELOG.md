# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.1.5]

### Added
- Added functionality to `prep_rtc.py` and `upload_rtc.py` to accept co-pol SLCs or bursts. 

## [0.1.4]

### Changed
- Updated DEM fetching/tiling strategy to match OPERA's.
- Updated DEM bounds buffer to 100 km from 0.025 degrees
- Updated burst database to the OPERA-provided burst_db_0.2.0_230831-bbox-only.sqlite file
- Updated our [PGE RunConfig template](./src/hyp3_opera_rtc/templates/pge.yml.j2) to more closely align with the [upstream version](https://github.com/nasa/opera-sds-pcm/blob/9bd74458957197b0c6680540c8d09c26ffab81df/conf/RunConfig.yaml.L2_RTC_S1.jinja2.tmpl).

## [0.1.3]

### Changed
- Download opera burst db during container build instead of at runtime.
- Publish docker container to public GHCR repo instead of private Amazon ECR repo.

## [0.1.2]

### Changed
- Added `_dir` to end of input, scratch, and work directories to match OPERA setup
- Upgraded to hyp3lib v4.

## [0.1.1]

### Changed
- All files in zip now contained in folder named after the product
- Remove `log` and `catalog.json` from the zip
- Switch to a full-SLC based data prep strategy

## [0.1.0]

### Added
- Added a Docker container that serves as a HyP3 plugin for OPERA-RTC processing.
