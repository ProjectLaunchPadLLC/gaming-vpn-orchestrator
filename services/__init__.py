"""Services layer for Gaming VPN Orchestrator.

Decoupled, independently testable services that handle all business logic:
- Telemetry collection (real metrics from system)
- VPN management (WireGuard control)
- Traffic classification
- Worker orchestration
- Event dispatching
- Configuration management
- Notifications

The UI consumes services via the event bus—never owns logic.
"""

__version__ = "0.1.0"
