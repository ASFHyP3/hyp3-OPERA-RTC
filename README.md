# HyP3 OPERA-RTC

A HyP3 plugin for OPERA-RTC processing

**ALL CREDIT FOR THIS PLUGIN'S RTC PRODUCTS GOES TO THE [JPL OPERA TEAM](https://www.jpl.nasa.gov/go/opera). THIS PLUGIN MERELY ALLOWS US TO RUN THEIR WORKFLOW IN A HYP3 ENVIRONMENT.**

## Earthdata Login Credentials

To use this plugin, the user must provide their Earthdata Login credentials in order to download input data.

If you do not already have an Earthdata account, you can sign up [here](https://urs.earthdata.nasa.gov/home).

Your credentials can be passed to the workflows via environmental variables that are passed to the docker container (`EARTHDATA_USERNAME`, and `EARTHDATA_PASSWORD`)

## Usage

This plugin is designed to run within the HyP3 processing system,
and directly relies on the JPL OPERA OPERA-RTC-S1 Product Generation Executable (PGE) docker container (see architecture section below).
For this reason, the plugin is only runnable via the docker container.

Build the container:

```bash
git clone https://github.com/ASFHyP3/hyp3-OPERA-RTC.git
cd hyp3-OPERA-RTC
docker build --platform linux/amd64 -t hyp3-opera-rtc:latest .
```

Then run the container:

```bash
docker run -it --rm \
    -e EARTHDATA_USERNAME=[YOUR_USERNAME_HERE] \
    -e EARTHDATA_PASSWORD=[YOUR_PASSWORD_HERE] \
    hyp3-opera-rtc:latest \
    [CO_POL_GRANULE]
```

Where you replace `[CO_POL_GRANULE]` with the name of the Sentinel-1 co-pol burst SLC scene
for which to generate the OPERA RTC product.
Here are some useful examples:

- `S1_146160_IW1_20241029T095958_VV_592B-BURST`: generates a VV product
- `S1_073251_IW2_20250413T020809_VV_EF1E-BURST`: generates a VV+VH product
- `S1_152193_IW3_20250415T143714_HH_EF65-BURST`: generates an HH product
- `S1_241258_IW1_20250418T105137_HH_57A0-BURST`: generates an HH+HV product

## Architecture

The plugin is composed of three nested docker environments that depend on eachother. They are laid out as below:

```
+-------------------------+
|       HyP3 (ASF)        |
|  +-------------------+  |
|  |    PGE (OPERA)    |  |
|  |  +-------------+  |  |
|  |  |             |  |  |
|  |  | SAS (OPERA) |  |  |
|  |  |             |  |  |
|  |  +-------------+  |  |
|  |                   |  |
|  +-------------------+  |
|                         |
+-------------------------+
```

The Alaska Satellite Facility's Hybrid Pluggable Processing Pipeline (HyP3) container is housed in this repository. It is responsible for marshalling the input data, calling the OPERA PGE container, and uploading the results to an S3 bucket. It takes the place of the Process Control & data Management (PCM) container that would be used within JPL's Science Data System (SDS).

The Product Generation Executable (PGE) container was created by the OPERA JPL team and is housed in the [nasa/opera-sds-pge](https://github.com/nasa/opera-sds-pge) repository. It is responsible for calling the OPERA SAS container and creating the sidecar iso.xml and STAC JSON metadata files.

The Science Algorithm Software (SAS) container was created by the OPERA JPL team and is housed in the [opera-adt/rtc](https://github.com/opera-adt/rtc) repository. It is responsible for performing the actual RTC calculations and creating the HDF5 metadata file.
