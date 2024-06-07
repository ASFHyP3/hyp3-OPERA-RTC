# HyP3 OPERA-RTC

**ALL CREDIT FOR THIS PLUGIN'S RTC PROCESSING GOES TO THE JPL OPERA TEAM. THIS PLUGIN MERELY ALLOWS US TO RUN THEIR WORKFLOW IN A HYP3 ENVIRONMENT.**

HyP3 plugin for OPERA-RTC processing

## Earthdata Login and ESA Credentials

To use this plugin, the user must provide their Earthdata Login credentials and ESA Copernicus Data Space Ecosystem (CDSE) credentials in order to download input data.

If you do not already have an Earthdata account, you can sign up [here](https://urs.earthdata.nasa.gov/home).

If you do not already have a CDSE account, you can sign up [here](https://dataspace.copernicus.eu).

Your credentials can be passed to the workflows via environmental variables that are passed to the docker container (`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`, `ESA_USERNAME`, and `ESA_PASSWORD`).

If you haven't set up a `.netrc` file
before, check out this [guide](https://harmony.earthdata.nasa.gov/docs#getting-started) to get started.

## Usage
This plugin is designed to run within the HyP3 processing system, and directly relies on the JPL OPERA OPERA-RTC-S1 Product Generation Executable (PGE) docker container. Currently, this container is not publicly available, but it likely will be in the near future.

For this reason, the plugin is only runnable via the docker container.

To do this, first build the container locally (assuming you have access to the opera_pge/rtc_s1:2.1.1 container):
```bash
git clone https://github.com/ASFHyP3/hyp3-OPERA-RTC.git
cd hyp3-OPERA-RTC
docker build -t hyp3-opera-rtc:latest .
```
Then run the container:
```bash
docker run -it --rm \
    -e EARTHDATA_USERNAME=[YOUR_USERNAME_HERE] \
    -e EARTHDATA_PASSWORD=[YOUR_PASSWORD_HERE] \
    -e ESA_USERNAME=[YOUR_USERNAME_HERE] \
    -e ESA_PASSWORD=[YOUR_PASSWORD_HERE] \
    hyp3-opera-rtc:latest ++process opera_rtc \
    S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F
```
Where you replace `S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F` with your desired SLC to generate OPERA RTC granules for.

All options for the workflow can be explored by calling `docker run -it --rm hyp3-opera-rtc:latest ++process opera_rtc --help`.

## Architecture
The plugin is composed of three nested docker environments that depend on eachother. They are laid out as below:

```
+-------------------------+
|        HyP3 (ASF)       |
|  +-------------------+  |
|  |     PGE (JPL)     |  |
|  |  +-------------+  |  |
|  |  |             |  |  |
|  |  |  SAS (JPL)  |  |  |
|  |  |             |  |  |
|  |  +-------------+  |  |
|  |                   |  |
|  +-------------------+  |
|                         |
+-------------------------+
```
