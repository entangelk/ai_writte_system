# Deploy Elasticsearch with the Korean morphological analyzer (nori). The
# official image does not bundle analysis-nori, so it is installed here at build
# time. The version is pinned to the one the lexical live smoke verified against
# real nori (ES 8.13.4) and can be overridden via the ELASTICSEARCH_VERSION build
# arg (mirrors CHROMA_VERSION for chroma).
ARG ELASTICSEARCH_VERSION=8.13.4
FROM docker.elastic.co/elasticsearch/elasticsearch:${ELASTICSEARCH_VERSION}

RUN bin/elasticsearch-plugin install --batch analysis-nori
