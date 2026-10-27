# Image build provenance

The profile currently uses `ghinwa555/oai-gnb-e2-chan:v2` and
`ghinwa555/oai-nr-ue-chan:v2`. Their Dockerfiles, source revisions, patch sets,
and complete build commands are not recorded here. An exact rebuild is therefore
not currently reproducible. Do not infer the gNB source from the core checkout.

The core setup pins OAI `70508ebaf52f2aae420566d380c6537f2efb9f0c`
and FlexRIC `ef6d722f22191eea74089966983da1f5ec1fedd4` for the host RIC build.
These revisions do not establish the provenance of either radio image.
`Dockerfile.flexric` is a reference for a containerised RIC, not a radio build.

Before replacing images, collect the running container image IDs and inspect
those exact IDs, rather than a mutable tag. Use `bin/collect-cell-evidence.py`.
Missing revision labels remain an unresolved provenance gap. A digest identifies
an artifact; it does not prove its source or RLC buffer configuration.

For future radio builds, archive the Dockerfiles, full source and submodule
revisions, patches, build flags, compiler versions, and resulting registry digests.
Include `org.opencontainers.image.revision` and `org.opencontainers.image.source`
labels. Pin verified image digests only after testing attachment, E2 indications,
and per-UE channel read-back. Never invent a revision or digest for existing images.
