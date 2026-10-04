"""Adapters: the edge of the hexagon.

Everything here implements a domain port using a concrete technology — the LLM (deterministic
rule engine or the Anthropic SDK), the telemetry transport (in-process fake, HTTP, gRPC), and
the clock/id sources. The domain depends only on the ports; :mod:`aql.factory` wires the
adapters in.
"""

from __future__ import annotations
