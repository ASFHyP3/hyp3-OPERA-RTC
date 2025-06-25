# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.1.4]

### Added
- DEM creation CLI entrypoint for debugging

### Changed
- Update DEM fetching/tiling strategy to match OPERA's.
- Updated DEM bounds buffer to 100 km from 0.025 degrees

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
