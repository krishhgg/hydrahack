# Thin wrapper over the published HydraDB engine image (ELv2, not vendored).
# Pinned by digest so CI and deploy never rebuild the Rust engine.
# Upstream: https://github.com/hydra-db/hydradb (release v0.4.0, commit 9166374).
ARG HYDRADB_IMAGE=ghcr.io/hydra-db/hydradb@sha256:ab71d651fefee13ebb23eb56d72316065bdca563ff7587442e07be663f2bf880
FROM ${HYDRADB_IMAGE}

USER root
RUN mkdir -p /data/store /data/cache /run/hydradb && chown -R 10001:10001 /data /run/hydradb
COPY infra/hydradb/entrypoint.sh /usr/local/bin/hydradb-entrypoint
COPY infra/hydradb/healthcheck.sh /usr/local/bin/hydradb-healthcheck
RUN chmod 0755 /usr/local/bin/hydradb-entrypoint /usr/local/bin/hydradb-healthcheck

ENV CLOUD_PROVIDER=local \
    LOCAL_PATH=/data/store \
    GRAPH_DATA_CACHE_DIR=/data/cache \
    GRAPH_NAMESPACE=default \
    GRAPH_ID=default \
    GRAPH_CELL_ID=cell-0 \
    GRAPH_CELLS=cell-0 \
    GRAPH_NODE_ID=node-0 \
    GRAPH_BOLT_NODE_ADDRESSES=node-0=hydradb:7687 \
    GRAPH_ADVERTISED_BOLT_ADDR=hydradb:7687 \
    GRAPH_ALLOW_PLAINTEXT=true \
    GRAPH_USAGE_REPORT_ENABLED=false \
    GRAPH_WAL_FLUSH_INTERVAL_MS=2 \
    RUST_MIN_STACK=33554432

VOLUME /data
USER 10001:10001
EXPOSE 7687 8443 9090
HEALTHCHECK --interval=5s --timeout=5s --start-period=5s --retries=20 CMD ["/usr/local/bin/hydradb-healthcheck"]
ENTRYPOINT ["/usr/local/bin/hydradb-entrypoint"]
