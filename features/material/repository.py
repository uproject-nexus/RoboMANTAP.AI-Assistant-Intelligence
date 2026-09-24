"""Material persistence service boundary."""
from infrastructure.database.materials import save_material_bundle_to_db, get_material_bundle_from_db
__all__=['save_material_bundle_to_db','get_material_bundle_from_db']
