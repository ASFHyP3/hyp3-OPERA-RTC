# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1]

### Changed
- The [`static-analysis`](.github/workflows/static-analysis.yml) Github Actions workflow now uses `ruff` rather than `flake8` for linting.
- Remove earthaccess dependency in favor of hyp3lib

## [0.1.0]

### Added
* working Dockerfile
* capability to stage data for full-slc OPERA RTC run
* capability to stage data for a burst OPERA RTC run
* capability to run OPERA RTC from within docker container

