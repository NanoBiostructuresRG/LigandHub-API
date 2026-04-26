# Changelog

All notable changes to LigandHub-API will be documented in this file.

## [v0.1.1-dev] - In development

### Planned

- Reorganize the backend codebase to separate API routes, configuration, validation logic, ligand preparation logic, batch processing, file handling, and docking-output conversion.
- Preserve compatibility with LigandHub frontend v0.1.0.
- Keep the current public API contract unchanged during the refactor.
- Maintain the existing workflows for ligand preparation, structural validation, batch processing, and docking-output conversion.

### Changed

- Extracted backend configuration constants into `config.py`.
- Extracted small utility helpers into `utils.py`.
- Preserved the public API contract from v0.1.0 during the first refactor step.
- Extracted chemical and SMILES validation logic into `validation.py`.
- Extracted docking result format detection and PDBQT/DLG-to-SDF conversion logic into `docking_io.py`.
- Added local temporary test folder pattern `tmp_test/` to `.gitignore`.
- Extracted upload file handling logic into `file_io.py`.
- Extracted molecule loading logic into `molecule_io.py`.
- Extracted the RDKit geometry, hydrogen addition, and minimization helper into `preparation.py`.
- Moved scrubbed molecule state generation into `preparation.py`, keeping batch endpoint behavior unchanged.
- Extracted duplicated PDBQT string writing into `pdbqt_writer.py`.
- Extracted Meeko molecule setup generation into `pdbqt_writer.py`, preserving endpoint-level preparation flow and batch behavior.
- Extracted batch SMILES parsing logic into `batch_processing.py`.
- Extracted batch summary construction into `batch_processing.py`.
- Extracted batch archive filename construction into `batch_processing.py`.
- Extracted batch ZIP response generation into `batch_processing.py`.
- Updated `Dockerfile` to copy the full backend codebase using `COPY . .`, ensuring all refactored modules are included in the container build.
- Cleaned malformed comments (mojibake) in `Dockerfile` without altering functional instructions.
- Added `.dockerignore` to exclude caches, virtual environments, development artifacts, and large non-essential files from the Docker build context.


### Notes

This development version focuses on internal backend restructuring. It does not intentionally introduce changes to frontend behavior or public endpoint usage.

- Minimal local regression test completed after modular extraction: `/health`, `/limits`, `/validate`, `/prepare_ligand`, and `/convert_pdbqt_to_sdf` passed.
- Local functional checks passed for individual ligand preparation and batch ligand preparation after extracting the preparation helper.
- Local functional checks passed for batch ligand preparation and individual ligand preparation after extracting `scrub_molecule_states`.
- Local functional checks passed for individual and batch ligand preparation after extracting the PDBQT writer helper.
- Local functional checks passed for individual and batch ligand preparation after extracting the Meeko setup helper.
- Local functional checks passed for batch ligand preparation after extracting SMILES parsing helper.
- Local functional checks passed for batch ligand preparation after extracting the batch summary helper.
- Local functional checks passed for batch ligand preparation after extracting archive naming helper.
- Local functional checks passed for batch ligand preparation after extracting ZIP response helper.
- Docker build could not be validated locally due to Docker not being available in the execution environment.
- The current repository structure and Docker configuration are ready for deployment testing on Render.



## [v0.1.0] - 2026-04-25

### Added

- Initial backend API release for LigandHub.
- Health and limits endpoints.
- SMILES validation endpoint.
- Individual ligand preparation workflow.
- Batch ligand preparation workflow for SMILES libraries.
- Docking-output conversion workflow from PDBQT or DLG to SDF.
- Conservative upload-size and library-size limits for the prototype deployment.

### Notes

This release defines the first backend baseline compatible with LigandHub frontend v0.1.0.