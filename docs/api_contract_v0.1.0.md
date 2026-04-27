# LigandHub-API Public Contract v0.1.0

This document records the public API endpoints available in LigandHub-API v0.1.0. These endpoints are used as the compatibility baseline for backend development toward v0.1.1.

## Public Endpoints

- `/`
- `/health`
- `/limits`
- `/validate`
- `/prepare_ligand`
- `/prepare_ligand_batch`
- `/convert_pdbqt_to_sdf`

## Compatibility Rule for v0.1.1

Backend v0.1.1 may reorganize the internal code structure, but it should preserve the public API contract used by LigandHub frontend v0.1.0.

This means that endpoint paths, expected request fields, response formats, and frontend-facing behavior should not be changed intentionally during the v0.1.1 refactor.