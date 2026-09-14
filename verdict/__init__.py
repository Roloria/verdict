"""verdict — deterministic quality gates for AI output.

Fork of reverify (MIT, 2akouwu). reverify checks claims about binaries; verdict
reuses the same claim -> deterministic-tool -> evidence protocol and points it at
the things AI actually produces: reports, docs, diffs, generated files.

The reverify/ package is never modified, so upstream merges stay conflict-free.
Every new gate is a `_check_<kind>` method on GateVerifier.
"""

__version__ = "0.1.0"

from .verifier import GateVerifier, TEXT_KINDS, rescore

__all__ = ["GateVerifier", "TEXT_KINDS", "rescore", "__version__"]
