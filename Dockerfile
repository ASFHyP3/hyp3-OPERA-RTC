FROM ghcr.io/nasa/opera-sds-pge/opera_pge/rtc_s1:2.1.3

# For opencontainers label definitions, see:
#    https://github.com/opencontainers/image-spec/blob/master/annotations.md
LABEL org.opencontainers.image.title="HyP3 OPERA-RTC"
LABEL org.opencontainers.image.description="HyP3 plugin for OPERA-RTC processing"
LABEL org.opencontainers.image.vendor="Alaska Satellite Facility"
LABEL org.opencontainers.image.authors="tools-bot <UAF-asf-apd@alaska.edu>"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"
LABEL org.opencontainers.image.url="https://github.com/ASFHyP3/hyp3-OPERA-RTC"
LABEL org.opencontainers.image.source="https://github.com/ASFHyP3/hyp3-OPERA-RTC"
LABEL org.opencontainers.image.documentation="https://hyp3-docs.asf.alaska.edu"

USER root
RUN chown rtc_user:rtc_user /home/rtc_user/scratch
USER rtc_user

RUN curl https://asf-dem-west.s3.amazonaws.com/AUX/burst_db_0.2.0_230831-bbox-only.sqlite -o /home/rtc_user/burst_db_0.2.0_230831-bbox-only.sqlite

COPY --chown=rtc_user:rtc_user . /home/rtc_user/hyp3-opera-rtc/
RUN conda env create -f /home/rtc_user/hyp3-opera-rtc/environment.yml && \
    conda clean -afy && \
    sed -i 's/conda activate RTC/conda activate hyp3-opera-rtc/g' /home/rtc_user/.bashrc && \
    conda run -n hyp3-opera-rtc python -m pip install --no-cache-dir /home/rtc_user/hyp3-opera-rtc

WORKDIR /home/rtc_user
ENTRYPOINT ["/home/rtc_user/hyp3-opera-rtc/src/hyp3_opera_rtc/etc/entrypoint.sh"]
CMD ["-h"]
