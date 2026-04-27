MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
MAX_BATCH_UPLOAD_SIZE_BYTES = 1 * 1024 * 1024
MAX_BATCH_MOLECULES = 100
MAX_SCRUBBED_STATES_PER_LIGAND = 8
MAX_BATCH_PDBQT_FILES = 250
MAX_BATCH_TOTAL_PDBQT_BYTES = 25 * 1024 * 1024
DEFAULT_MINIMIZATION_MAX_ITERS = 1000
MAX_MINIMIZATION_MAX_ITERS = 2000
SUPPORTED_CHARGE_MODELS = {"gasteiger", "nagl", "espaloma", "zero"}
COMMON_ELEMENTS = {
    "H", "B", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I",
    "Li", "Na", "K", "Mg", "Ca", "Fe", "Zn", "Cu", "Mn", "Co", "Ni", "Al",
}
METALS = {"Fe", "Zn", "Cu", "Mn", "Co", "Ni", "Mg", "Ca", "Na", "K", "Li", "Al"}

ALLOWED_ORIGINS = [
    "https://nanobiostructuresrg.github.io",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
