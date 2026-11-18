# syntax=docker/dockerfile:1
# Private Qwen service for the end-of-practice feedback (docs/rag.md, "Model and hosting").
# llama.cpp's server, pinned to build b12464, with the official Qwen2.5-0.5B-Instruct Q4_K_M file
# pinned to a Hugging Face revision and checked against its SHA-256 while the image builds.
FROM ghcr.io/ggml-org/llama.cpp:server-b12464

ADD --checksum=sha256:74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db \
    https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    /models/qwen2.5-0.5b-instruct-q4_k_m.gguf

# The server reads LLAMA_ARG_* settings. On Railway set LLAMA_ARG_HOST to :: (private network).
ENV LLAMA_ARG_MODEL=/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    LLAMA_ARG_ALIAS=qwen2.5-0.5b-instruct-q4_k_m \
    LLAMA_ARG_HOST=0.0.0.0 \
    LLAMA_ARG_PORT=8080 \
    LLAMA_ARG_CTX_SIZE=2048 \
    LLAMA_ARG_N_PARALLEL=2 \
    LLAMA_ARG_THREADS=2

EXPOSE 8080
