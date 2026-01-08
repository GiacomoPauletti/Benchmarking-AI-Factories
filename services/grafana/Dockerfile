FROM grafana/grafana:latest

# Install chromium for reports, and wget/unzip for plugin installation
USER root
RUN apk add --no-cache chromium wget unzip
USER 472

RUN VERSION=1.10.0; grafana cli --pluginUrl "https://github.com/mahendrapaipuri/grafana-dashboard-reporter-app/releases/download/v${VERSION}/mahendrapaipuri-dashboardreporter-app-${VERSION}.zip" plugins install mahendrapaipuri-dashboardreporter-app

# Install plugins manually to avoid IPv6 issues in build environment
RUN cd /var/lib/grafana/plugins && \
    wget -4 -O infinity.zip https://grafana.com/api/plugins/yesoreyeram-infinity-datasource/versions/latest/download && \
    unzip infinity.zip && \
    rm infinity.zip && \
    wget -4 -O form-panel.zip https://grafana.com/api/plugins/volkovlabs-form-panel/versions/latest/download && \
    unzip form-panel.zip && \
    rm form-panel.zip

COPY grafana.ini /etc/grafana/grafana.ini
COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards