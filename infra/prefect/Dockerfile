FROM prefecthq/prefect:3-python3.12

WORKDIR /workspace

COPY ./workloads/orchestration ./workloads/orchestration

RUN pip install \
    ray[default]==2.51.1

EXPOSE 4200
