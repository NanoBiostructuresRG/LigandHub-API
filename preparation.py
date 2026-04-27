import logging

from fastapi import HTTPException
from rdkit import Chem
from rdkit.Chem import AllChem

from config import DEFAULT_MINIMIZATION_MAX_ITERS, MAX_SCRUBBED_STATES_PER_LIGAND
from utils import get_batch_limit_summary

try:
    from molscrub import Scrub
except ImportError:
    Scrub = None


logger = logging.getLogger(__name__)


def ensure_3d_and_hydrogens(
    mol,
    energy_minimization: bool | None = None,
    minimization_max_iters: int = DEFAULT_MINIMIZATION_MAX_ITERS,
):
    input_has_3d = (
        mol.GetNumConformers() > 0 and
        mol.GetConformer().Is3D()
    )

    # Add Hs explicit; addCoords helps preserve coordinates when they exist
    mol = Chem.AddHs(mol, addCoords=True)

    needs_3d = (
        mol.GetNumConformers() == 0 or
        not mol.GetConformer().Is3D()
    )

    if needs_3d:
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        embed_status = AllChem.EmbedMolecule(mol, params)

        if embed_status != 0:
            raise HTTPException(status_code=400, detail="RDKit could not generate 3D coordinates")

    should_minimize = energy_minimization if energy_minimization is not None else not input_has_3d

    if should_minimize:
        try:
            mmff_props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
            if mmff_props is not None:
                AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", maxIters=minimization_max_iters)
            elif AllChem.UFFHasAllMoleculeParams(mol):
                AllChem.UFFOptimizeMolecule(mol, maxIters=minimization_max_iters)
            else:
                logger.info("No MMFF94 or UFF parameters available; skipping ligand minimization")
        except Exception:
            logger.exception("Ligand minimization failed; continuing with current geometry")

    return mol


def scrub_molecule_states(
    mol,
    energy_minimization: bool | None = None,
    minimization_max_iters: int = DEFAULT_MINIMIZATION_MAX_ITERS,
):
    if Scrub is None:
        raise HTTPException(
            status_code=500,
            detail="molscrub is not installed in the runtime environment",
        )

    scrubber = Scrub(ph_low=7.4, ph_high=7.4)
    scrubbed_states = list(scrubber(mol))

    if not scrubbed_states:
        raise HTTPException(status_code=400, detail="Scrub could not generate any ligand state")

    if len(scrubbed_states) > MAX_SCRUBBED_STATES_PER_LIGAND:
        raise HTTPException(
            status_code=413,
            detail={
                "message": (
                    "Scrub generated too many states for this ligand for the current prototype limit. "
                    f"Maximum allowed states per ligand: {MAX_SCRUBBED_STATES_PER_LIGAND}"
                ),
                "suggestion": "Process this ligand separately or reduce the batch complexity.",
                "limits": get_batch_limit_summary(),
            },
        )

    prepared_states = []
    for state in scrubbed_states:
        state_with_geometry = ensure_3d_and_hydrogens(
            state,
            energy_minimization=energy_minimization,
            minimization_max_iters=minimization_max_iters,
        )
        prepared_states.append(state_with_geometry)

    return prepared_states
