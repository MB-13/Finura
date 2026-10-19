# Inference worker: the backend image + llama.cpp (llama-server and convert_lora_to_gguf.py), CPU build.
# Build from the repo root:  docker build -f infra/inference.Dockerfile --build-arg BASE=ghcr.io/ORG/doctune-backend:TAG .
ARG BASE=doctune-backend:latest
ARG LLAMA_CPP_REF=b10646

FROM debian:bookworm-slim AS llama
ARG LLAMA_CPP_REF
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates libcurl4-openssl-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${LLAMA_CPP_REF} https://github.com/ggml-org/llama.cpp /opt/llama.cpp
WORKDIR /opt/llama.cpp
# GGML_NATIVE tunes for the build machine's CPU; build on (or for) the Ampere A1 target
RUN cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=ON -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build --config Release -j"$(nproc)" --target llama-server

FROM ${BASE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=llama /opt/llama.cpp/build/bin /opt/llama.cpp/build/bin
COPY --from=llama /opt/llama.cpp/convert_lora_to_gguf.py /opt/llama.cpp/convert_hf_to_gguf.py /opt/llama.cpp/
COPY --from=llama /opt/llama.cpp/gguf-py /opt/llama.cpp/gguf-py
COPY --from=llama /opt/llama.cpp/conversion /opt/llama.cpp/conversion
COPY --from=llama /opt/llama.cpp/requirements /opt/llama.cpp/requirements
# convert_lora_to_gguf.py needs CPU torch + transformers; keep them in their own venv, out of the API's
RUN uv venv --python 3.12 /opt/llama.cpp/.venv \
 && uv pip install --python /opt/llama.cpp/.venv/bin/python --index-strategy unsafe-best-match \
      -r /opt/llama.cpp/requirements/requirements-convert_lora_to_gguf.txt \
 && uv pip install --python /opt/llama.cpp/.venv/bin/python -e /opt/llama.cpp/gguf-py
USER doctune
