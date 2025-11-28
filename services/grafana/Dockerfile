FROM grafana/grafana:latest

# Install chromium for reports
USER root
RUN apk add --no-cache chromium
USER 472

RUN VERSION=1.10.0; grafana cli --pluginUrl "https://github.com/mahendrapaipuri/grafana-dashboard-reporter-app/releases/download/v${VERSION}/mahendrapaipuri-dashboardreporter-app-${VERSION}.zip" plugins install mahendrapaipuri-dashboardreporter-app

COPY grafana.ini /etc/grafana/grafana.ini
COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards