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


### Notes

This development version focuses on internal backend restructuring. It does not intentionally introduce changes to frontend behavior or public endpoint usage.

- Minimal local regression test completed after modular extraction: `/health`, `/limits`, `/validate`, `/prepare_ligand`, and `/convert_pdbqt_to_sdf` passed.
- Local functional checks passed for individual ligand preparation and batch ligand preparation after extracting the preparation helper.


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