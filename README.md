# LigandHub-API

Backend API for ligand preparation and docking-result conversion in LigandHub.

This service is built with FastAPI and is intended to run on Render. It prepares ligands for AutoDock Vina workflows using RDKit, Meeko, and `molscrub`, and it can also convert docking outputs back to SDF.

Current development state: `v0.1.2`.

## What This API Does

LigandHub-API currently preserves the public HTTP endpoints used by the v0.1.0 frontend:

- `GET /health`: basic service health check with RDKit and Meeko availability
- `GET /limits`: returns the current prototype limits configured for Render deployment
- `POST /validate`: validates one SMILES string without running ligand preparation
- `POST /prepare_ligand`: prepares a single ligand and returns a `.pdbqt`
- `POST /prepare_ligand_batch`: prepares a SMILES library and returns a ZIP with multiple `.pdbqt`
- `POST /convert_pdbqt_to_sdf`: converts docking result files (`.pdbqt` or `.dlg`) back to `.sdf`

## Core Workflows

### 1. Single-ligand preparation

Supported input formats:

- `.sdf`
- `.mol2`
- `.pdb`
- `.smi`
- `.smiles`
- `.txt`

Pipeline:

```text
Input molecule
   ->
RDKit parsing
   ->
structural validation
   ->
3D coordinates + explicit hydrogens
   ->
optional energy minimization
   ->
Meeko preparation
   ->
PDBQT output
```

### 2. Batch ligand preparation

Supported batch input:

- `.smi`
- `.smiles`
- `.txt`

Expected format per line:

```text
SMILES LIGAND_ID
```

Batch pipeline:

```text
.smi library
   ->
line-by-line SMILES parsing
   ->
structural validation
   ->
Scrub / molscrub
   ->
enumerated ligand states
   ->
optional energy minimization
   ->
Meeko preparation
   ->
multiple PDBQT files
   ->
ZIP response + summary.json
```

### 3. Docking-result recovery

Supported input formats:

- `.pdbqt`
- `.dlg`

Pipeline:

```text
Docking result file
   ->
Meeko reconstruction
   ->
RDKit molecules
   ->
SDF output
```

## Structural Validation

LigandHub validates molecular structure before ligand preparation starts. This keeps common input problems out of the Meeko step and gives clients errors that can be shown directly to users.

Validation covers:

- SMILES syntax problems, including unclosed rings, brackets, and parentheses
- atom valence errors reported with atom index, element, observed valence, and typical maximum valence when available
- metal atoms that may need explicit charge review
- unusual elements outside the common ligand-preparation set
- high formal net charge

Fatal validation errors stop ligand preparation with a `400` response. Non-fatal findings are returned as warnings so the frontend can let the user decide whether the molecule still makes chemical sense for their workflow.

## API Endpoints

### `GET /health`

Example:

```bash
curl http://localhost:8000/health
```

Returns:

```json
{
  "status": "ok",
  "rdkit": true,
  "meeko": true
}
```

### `GET /limits`

Returns the active server-side limits for this prototype deployment.

Example:

```bash
curl http://localhost:8000/limits
```

Example response:

```json
{
  "service_mode": "prototype",
  "notes": [
    "Batch limits are intentionally conservative for a small Render deployment.",
    "If you need larger libraries, move batch processing to an async worker or workflow."
  ],
  "limits": {
    "single_upload_max_bytes": 10485760,
    "batch_upload_max_bytes": 1048576,
    "batch_max_molecules": 100,
    "batch_max_scrubbed_states_per_ligand": 8,
    "batch_max_generated_pdbqt_files": 250,
    "batch_max_total_pdbqt_bytes": 26214400
  }
}
```

### `POST /prepare_ligand`

Prepares one ligand and returns a `.pdbqt` file.
The input is validated before 3D coordinate generation and Meeko preparation. Validation warnings are returned in the `X-LigandHub-Warnings` response header as a JSON array of messages.

Form fields:

- `file`: required input file
- `filename`: optional output basename, default `ligand`
- `output_format`: currently only `pdbqt`
- `merge_h`: `true` or `false`
- `charge_model`: `gasteiger`, `nagl`, `espaloma`, or `zero`
- `energy_minimization`: optional `true` or `false`; when omitted, minimization is enabled for SMILES/2D inputs and disabled for 3D input files
- `minimization_max_iters`: optional integer from `1` to `2000`, default `1000`

Energy minimization uses MMFF94 when parameters are available and falls back to UFF when MMFF94 cannot be assigned. If neither force field can be applied, ligand preparation continues with the current geometry.

Example:

```bash
curl -X POST http://localhost:8000/prepare_ligand \
  -F "file=@ligand.sdf" \
  -F "filename=my_ligand" \
  -F "merge_h=true" \
  -F "charge_model=gasteiger" \
  -F "energy_minimization=true" \
  -F "minimization_max_iters=1000" \
  --output my_ligand_prepared.pdbqt
```

### `POST /validate`

Validates one SMILES string without running ligand preparation.

Form fields:

- `smiles`: required SMILES string

Example:

```bash
curl -X POST http://localhost:8000/validate \
  -F "smiles=CCO"
```

Example response:

```json
{
  "valid": false,
  "errors": [
    {
      "type": "valence_error",
      "atom": 1,
      "element": "C",
      "valence": 5,
      "max_valence": 4,
      "message": "C atom #1 has valence 5 (typical max 4)"
    }
  ],
  "warnings": [],
  "smiles": "C(C)(C)(C)(C)C"
}
```

### `POST /prepare_ligand_batch`

Prepares a SMILES library and returns a ZIP archive containing:

- one `.pdbqt` file per generated ligand state
- `summary.json` with success/failure details, including validation errors and warnings per ligand

Form fields:

- `file`: required `.smi`, `.smiles`, or `.txt` library
- `filename`: optional output basename, default `ligands`
- `merge_h`: `true` or `false`
- `charge_model`: `gasteiger`, `nagl`, `espaloma`, or `zero`
- `energy_minimization`: optional `true` or `false`; when omitted, minimization is enabled for generated 3D geometries
- `minimization_max_iters`: optional integer from `1` to `2000`, default `1000`

Energy minimization uses MMFF94 when parameters are available and falls back to UFF when MMFF94 cannot be assigned. If neither force field can be applied, batch processing continues with the current geometry for that ligand state.

Example input:

```text
CCO ethanol
CCN ethylamine
c1ccccc1 benzene
```

Example:

```bash
curl -X POST http://localhost:8000/prepare_ligand_batch \
  -F "file=@library.smi" \
  -F "filename=demo_library" \
  -F "merge_h=true" \
  -F "charge_model=gasteiger" \
  -F "energy_minimization=true" \
  -F "minimization_max_iters=1000" \
  --output demo_library_pdbqt_batch.zip
```

Example error response for oversized or too-large batch jobs:

```json
{
  "detail": {
    "message": "Batch request exceeds the prototype limit of 100 molecules.",
    "suggestion": "Split the library into smaller files for this Render deployment.",
    "limits": {
      "batch_upload_max_bytes": 1048576,
      "batch_max_molecules": 100,
      "batch_max_scrubbed_states_per_ligand": 8,
      "batch_max_generated_pdbqt_files": 250,
      "batch_max_total_pdbqt_bytes": 26214400
    }
  }
}
```

Frontend integration note:

- for batch-limit errors, read `detail.message` and show it directly to the user
- show `detail.suggestion` as the recommended next action
- optionally render `detail.limits` in a help panel so users know when to split a library into smaller batches
- for validation errors, show `detail.message`; use `detail.errors` and `detail.warnings` when a more structured UI is useful

### `POST /convert_pdbqt_to_sdf`

Converts docking result files back to SDF.

Form fields:

- `file`: required `.pdbqt` or `.dlg`
- `filename`: optional output basename, default `docked_results`

Example:

```bash
curl -X POST http://localhost:8000/convert_pdbqt_to_sdf \
  -F "file=@vina_out.pdbqt" \
  -F "filename=vina_out" \
  --output vina_out_docked.sdf
```

## Prototype Limits For Render

This API is currently configured as a prototype deployment and uses conservative limits to avoid overloading a small Render instance.

Current limits:

- single-file upload max size: `10 MB`
- batch upload max size: `1 MB`
- max molecules per batch file: `100`
- max scrubbed states per ligand in batch mode: `8`
- max generated `.pdbqt` files per batch request: `250`
- max total generated `.pdbqt` payload before ZIP: `25 MB`

Why these limits exist:

- RDKit, `molscrub`, and Meeko can become CPU- and memory-heavy on large libraries
- batch ZIP generation is currently done in-process and in memory
- the service is intended for lightweight prototype usage on Render, not high-throughput screening

If larger jobs are needed, the recommended next step is to move batch processing to a background worker, queue, or workflow-based architecture.

## Dependencies

Key Python dependencies currently used by the API:

- `fastapi`
- `uvicorn`
- `python-multipart`
- `meeko`
- `rdkit`
- `molscrub`
- `scipy`
- `gemmi`

Testing dependencies are kept separate in `requirements-dev.txt`.

`v0.1.2` adds automated integration tests for `/prepare_ligand`, `/prepare_ligand_batch`, `/convert_pdbqt_to_sdf`, and negative input cases.

## Project Structure

The `v0.1.2` backend is organized into small modules while preserving the public API contract:

- `app.py`: FastAPI application and endpoint orchestration
- `config.py`: runtime limits, defaults, CORS origins, and supported options
- `validation.py`: SMILES and molecule validation
- `file_io.py`: upload file handling
- `molecule_io.py`: molecule loading from supported file formats
- `preparation.py`: 3D generation, hydrogens, minimization, and scrubbed states
- `pdbqt_writer.py`: Meeko setup generation and PDBQT writing
- `batch_processing.py`: batch SMILES parsing, summaries, archive names, and ZIP responses
- `docking_io.py`: docking-result format detection and SDF export
- `utils.py`: shared small helpers

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Install development/test dependencies:

```bash
pip install -r requirements-dev.txt
```

Run locally:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Then open:

```text
http://localhost:8000/docs
```

Run tests:

```bash
pytest
```

Pytest is also run through GitHub Actions CI on push and pull requests.

## Render Deployment Notes

This repository includes a `Dockerfile` that installs Python dependencies from `requirements.txt`.

Current deployment behavior:

- Render builds the container image
- the image installs all Python dependencies with `pip install -r requirements.txt`
- the API starts with Uvicorn

Because of this, dependency changes for deployment should be reflected in `requirements.txt`.

The local `v0.1.1` Docker image has been built and smoke-tested with the main endpoints. Development-only test dependencies remain outside `requirements.txt`.

## Current Scope

Included:

- single-ligand preparation to PDBQT
- batch ligand preparation to ZIP of PDBQT files
- structural validation for ligand inputs before Meeko preparation
- docking-output conversion from PDBQT or DLG to SDF
- explicit runtime limits endpoint for frontend visibility

Not included yet:

- receptor preparation
- asynchronous batch jobs
- persistent job history
- queued processing for large screening libraries

## Author

[Flavio F. Contreras-Torres](https://orcid.org/0000-0003-2375-131X), Tecnologico de Monterrey.

## License

Project-specific source code is licensed under the MIT License unless otherwise stated. See the LICENSE files for full details.

Third-party dependencies keep their own licenses:

- RDKit: BSD 3-Clause
- Meeko: LGPL v2.1 or later
- Gemmi: MPL 2.0 or LGPL v3
- molscrub: GPL v3


## Attribution
If you use or adapt this material, please provide appropriate credit to the original authors and repository:

> NanoBiostructures Research Group  
> GitHub: https://github.com/NanoBiostructuresRG