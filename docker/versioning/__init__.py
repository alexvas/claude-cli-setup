"""docker versioning — offline inventory model with constraint engine.

All versioning modules are consumed directly by the constructor facade
(``docker.constructor_cli``) and the launcher (``docker.launcher``).
No separate CLI entry point exists — ``docker/versions.py`` is a
compatibility-only re-export shim.
"""
