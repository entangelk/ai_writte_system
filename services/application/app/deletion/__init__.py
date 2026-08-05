"""Records that a project purge deliberately leaves behind.

D8-6 destroys the project graph; this package is for the narrow, owner-approved
exceptions that outlive it. Its rows are **not** children of the deleted project
— they key on ``_id`` or ``target_project_id``, never ``project_id``, because
``scripts/purge_reconciler.py`` discovers and deletes any collection carrying a
``project_id`` field.
"""
