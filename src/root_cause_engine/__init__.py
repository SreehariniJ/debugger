"""
root_cause_engine — Fault localization via dynamic program slicing
and execution trace analysis.
"""

from root_cause_engine.slicer import BackwardSlicer
from root_cause_engine.fault_localizer import FaultLocalizer

__all__ = ["BackwardSlicer", "FaultLocalizer"]
