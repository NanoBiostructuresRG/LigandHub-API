# Changelog

All notable changes to LigandHub-API will be documented in this file.

## [v0.1.8] - 2026-05-06

### Added

- Added endpoint regression tests confirming unexpected internal failures still return HTTP 500 for ligand preparation workflows.

### Fixed

- Ensured non-UTF-8 SMILES text uploads to `/prepare_ligand` return HTTP 400 instead of unexpected HTTP 500 errors.
- Ensured non-UTF-8 batch SMILES library uploads to `/prepare_ligand_batch` return HTTP 400 instead of unexpected HTTP 500 errors.

### Notes

- Preserved the existing successful ligand preparation and batch preparation behavior.
- This release only hardens expected error handling; it does not add new API features.

## [v0.1.7] - 2026-05-06

### Added

- Added endpoint regression tests for invalid and empty docking result files.

### Fixed

- Improved negative input handling for docking result conversion.
- Ensured invalid or empty `.pdbqt` and `.dlg` uploads to `/convert_pdbqt_to_sdf` return HTTP 400 instead of unexpected HTTP 500 errors.

### Notes

- Preserved the existing public API contract and successful conversion behavior.

## [v0.1.6] - 2026-05-05

### Added

- Added negative tests for invalid ligand input files.
- Confirmed `POST /prepare_ligand` returns `400` for invalid supported ligand files.

### Fixed

- Fixed unreadable or empty SDF inputs returning server errors instead of client errors.

## [v0.1.5] - 2026-05-05

### Added

- Added real molecule fixtures for `.smi`, `.sdf`, and `.pdb` ligand inputs.
- Added unit tests for `molecule_io.load_molecule_from_file`.
- Added an integration test for `POST /prepare_ligand` using an `.sdf` input file.

### Notes

- No public API changes were introduced.
- `.mol2` coverage was intentionally left out to keep this version small and stable.

## [v0.1.4] - 2026-05-04

### Added

- Added a repository line ending policy with `.gitattributes`.
- Added CI hygiene checks for whitespace and text line endings.
- Added unit tests for docking result format detection.
- Extended `/health` degraded tests to cover missing `rdkit`, `meeko`, and `molscrub`.
- Added tests for generated batch PDBQT file-count and byte-size limits.

## [v0.1.3] - 2026-05-04

### Changed

- Updated `GET /health` to report `status: "ok"` only when critical dependencies are available, and `status: "degraded"` otherwise.
- Added a `dependencies` object to `/health` with explicit `rdkit`, `meeko`, and `molscrub` availability.
- Preserved previous flat `/health` dependency keys such as `rdkit` and `meeko` for compatibility.
- Centralized minimal file extension validation in `file_io.py`.
- Normalized line endings and trailing whitespace in modified files.

### Added

- Added tests for negative validator cases, upload limits, invalid file extensions, fully failed batch jobs, and `file_io.py`.

## [v0.1.2] - 2026-04-29

### Added

- Added integration test coverage for `POST /prepare_ligand`.
- Added integration test coverage for `POST /prepare_ligand_batch`.
- Added integration test coverage for `POST /convert_pdbqt_to_sdf`.
- Added controlled negative endpoint input tests for ligand preparation and batch preparation.
- Added a GitHub Actions workflow to run pytest on push and pull requests.

### Changed

- Updated `GET /health` to report RDKit and Meeko availability while preserving `status: "ok"`.

## [v0.1.1] - 2026-04-29

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
- Added an initial unit test suite using pytest, covering core utility and validation modules.
- Introduced `requirements-dev.txt` to isolate development dependencies.
- Added `pytest.ini` for test configuration and standardized test discovery.
- Added basic endpoint smoke tests using FastAPI `TestClient` for `/health` and `/validate`.
- Extended basic endpoint smoke tests to cover `/limits`.
- Added `httpx` to development dependencies for FastAPI `TestClient` support.


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
- The current repository structure and Docker configuration are ready for deployment testing on Render.
- Docker image successfully built and validated locally; container execution and `/health` endpoint verified.
- Resolved risk: local Docker build validation is complete for `ligandhub-api:v0.1.1-dev`.
- Initial automated tests cover pure and low-risk modules: `validation.py`, `utils.py`, and `batch_processing.py`.
- Test suite executed successfully with all tests passing.
- Basic automated endpoint smoke tests cover `GET /health`, `GET /limits`, `POST /validate` with valid SMILES, and `POST /validate` with invalid SMILES using form data.
- Test suite executed successfully after adding the `/limits` smoke test: 24 tests passed.
- Modules tightly coupled to FastAPI (e.g., `file_io.py`) were intentionally excluded from this first testing layer.
- The initial testing gap has been partially mitigated with a pytest-based unit test suite.
- Docker-based endpoint smoke test completed successfully for `/health`, `/limits`, `/validate`, `/prepare_ligand`, and `/prepare_ligand_batch`; individual and batch PDBQT generation were verified.
- Pytest suite was validated inside a temporary Docker container using the existing `ligandhub-api:v0.1.1-dev` image with the current workspace mounted; all tests passed.
- Remaining risks: automated coverage is still initial; integration/endpoint tests and RDKit/Meeko-heavy workflows are still pending.
- Remaining risks: `batch_processing.py` remains a critical area because it coordinates flow control, limits, ZIP generation, per-molecule errors, and result accumulation.
- Remaining risks: `file_io.py` still needs async tests with mocks or stubs for `UploadFile`.
- The Docker image was rebuilt after adding the test suite, and pytest was successfully executed inside the updated container image.
- Remaining risks: Docker-based pytest execution is validated but still manual; it should be automated in a repeatable local or CI workflow.
- Remaining risks: endpoint smoke tests still need to be automated for `/prepare_ligand`, `/prepare_ligand_batch`, and `/convert_pdbqt_to_sdf`.
- Note: if validation notes continue to grow, move detailed diagnostic history into a separate docs file and keep this changelog focused on release-level changes.




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
