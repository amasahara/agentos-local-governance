from .reconciliation_recovery import migration_40 as _m40
from .identity_resolution import migration_39 as _m39
from .controlled_target_insert import migration_38 as _m38
from .read_only_extraction import migration_37 as _m37
from .schema_mapping import migration_36 as _m36
from .database_boundary import migration_35 as _m35
from .project_consolidation import migration_34 as _m34
from .project_selection import migration_33 as _m33
from .project_identity import migration_32 as _m32
MIGRATIONS = [_m32, _m33, _m34, _m35, _m36, _m37, _m38, _m39, _m40]
