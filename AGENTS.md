# MPPS MAX PERFORMANCE POLICY

For every heavy operation, design and execute for MAXIMUM SAFE PRACTICAL PERFORMANCE from the beginning.

## Mandatory rules
- Use maximum useful CPU cores/threads and parallelism.
- Use RTX 4060 CUDA/GPU acceleration whenever the workload supports it.
- Optimize NVMe I/O, RAM/cache, PostgreSQL, database indexes, queries, batching and concurrency before long runs.
- Identify and remove bottlenecks before starting multi-hour operations.
- Avoid unnecessary serial processing, repeated full-table scans, duplicate work and weak default settings.
- Prefer checkpoint/resume architecture for long-running operations.
- Benchmark/verify configuration before committing to a long job.
- Target the shortest real completion time, not artificial 100% utilization.
- If a task is CPU-bound, maximize useful CPU utilization.
- If a task is GPU-capable, use CUDA efficiently.
- If a task is DB/I/O-bound, optimize the DB/query/storage path instead of wasting CPU/GPU.
- Never silently fall back to a slower implementation when a safe faster implementation is available.

## Quality and safety
Performance optimization MUST NOT reduce:
- data accuracy
- source truth
- ML model quality
- validation/leakage/chronology gates
- database durability
- code correctness
- reproducibility

Do NOT use:
- unsafe overclocking
- Realtime process priority
- corruption-risk database settings
- fake/invalid ML labels
- accuracy-reducing shortcuts
- artificial CPU/GPU load

Before any heavy MPPS task, inspect hardware/resources and choose the fastest safe architecture/configuration first.
