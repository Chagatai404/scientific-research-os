# PyTorch software guide

Use `references/ML_PROTOCOL.md` for methodology. Inspect APIs, release notes and
reproducibility guidance for the project-pinned version, not automatically latest.
Record dtype, device, train/eval mode, gradient mode, checkpoints, data-loader
workers and determinism settings with the declared run configuration. A seed alone
does not prove identical results across software/hardware changes.

Default discovery reads the `torch` distribution version without importing it.
`probe pytorch --accelerator` explicitly opts into a fixed, isolated Python child
that imports installed torch and queries CUDA/MPS availability and CUDA build
version; it does not allocate tensors or run GPU workloads. The installed package
must be trusted. Failure/timeout remains UNKNOWN, not CPU-only proof. A detected
backend does not select it for the experiment. CUDA is never required.

Prefer [official CUDA API documentation](https://docs.pytorch.org/docs/stable/generated/torch.cuda.is_available.html)
and [reproducibility notes](https://docs.pytorch.org/docs/stable/notes/randomness.html),
then official release notes/primary framework papers for framework claims. Scientific
comparison and uncertainty remain subject to ML_PROTOCOL and SOURCE_POLICY.
