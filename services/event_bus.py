"""Event Bus for Gaming VPN Orchestrator.

Decoupled event dispatcher that enables loose coupling between services.
All services communicate through events—no direct dependencies.

Example usage:

    bus = EventBus()
    
    # Subscribe to events
    bus.subscribe("vpn:connected", on_vpn_connected)
    bus.subscribe("metrics:updated", on_metrics_updated)
    
    # Emit events
    bus.emit("vpn:connected", {"endpoint": "10.0.0.1", "latency_ms": 25})
    bus.emit("metrics:updated", {"latency_ms": 25, "jitter_ms": 2.5})
"""

import logging
import threading
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class EventType(Enum):
    """All event types in the system."""
    
    # VPN Events
    VPN_CONNECTED = "vpn:connected"
    VPN_DISCONNECTED = "vpn:disconnected"
    VPN_CONNECTING = "vpn:connecting"
    VPN_ERROR = "vpn:error"
    VPN_STATUS_CHANGED = "vpn:status_changed"
    
    # Metrics Events
    METRICS_UPDATED = "metrics:updated"
    METRICS_ANOMALY = "metrics:anomaly"
    LATENCY_SPIKE = "metrics:latency_spike"
    PACKET_LOSS_DETECTED = "metrics:packet_loss_detected"
    
    # Traffic Events
    TRAFFIC_CLASSIFIED = "traffic:classified"
    GAMING_TRAFFIC_DETECTED = "traffic:gaming_detected"
    TRAFFIC_ANOMALY = "traffic:anomaly"
    
    # Worker Events
    WORKER_STARTED = "worker:started"
    WORKER_STOPPED = "worker:stopped"
    WORKER_ERROR = "worker:error"
    WORKER_DECISION = "worker:decision"
    WORKER_PAUSED = "worker:paused"
    WORKER_RESUMED = "worker:resumed"
    
    # Configuration Events
    CONFIG_LOADED = "config:loaded"
    PROFILE_CHANGED = "profile:changed"
    SETTINGS_UPDATED = "settings:updated"
    
    # System Events
    SYSTEM_STARTUP = "system:startup"
    SYSTEM_SHUTDOWN = "system:shutdown"
    SYSTEM_ERROR = "system:error"
    SYSTEM_WARNING = "system:warning"
    
    # Firewall Events
    FIREWALL_RULE_ADDED = "firewall:rule_added"
    FIREWALL_RULE_REMOVED = "firewall:rule_removed"
    
    # Routing Events
    ROUTE_ADDED = "routing:route_added"
    ROUTE_REMOVED = "routing:route_removed"
    
    # Notification Events
    NOTIFICATION_INFO = "notification:info"
    NOTIFICATION_WARNING = "notification:warning"
    NOTIFICATION_ERROR = "notification:error"
    NOTIFICATION_SUCCESS = "notification:success"


@dataclass
class Event:
    """Represents an event in the system."""
    
    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "system"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary.
        
        Returns:
            Dictionary representation of event
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.data,
        }


class EventBus:
    """Central event dispatcher for decoupled communication between services.
    
    Features:
    - Thread-safe event emission and subscription
    - Async event handling support
    - Event history tracking
    - Error handling and propagation
    - Priority-based event ordering
    """
    
    def __init__(self, max_history: int = 1000, enable_logging: bool = True):
        """Initialize the event bus.
        
        Args:
            max_history: Maximum number of events to keep in history
            enable_logging: Whether to log all events
        """
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._history: List[Event] = []
        self._max_history = max_history
        self._enable_logging = enable_logging
        self._stats = {
            "total_events": 0,
            "total_subscribers": 0,
        }
        logger.info("Event bus initialized")
    
    def subscribe(
        self,
        event_type: EventType,
        callback: Callable,
        priority: int = 0,
    ) -> str:
        """Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event is emitted
            priority: Priority level (higher = called first)
            
        Returns:
            Subscription ID for later unsubscription
        """
        with self._lock:
            event_key = event_type.value if isinstance(event_type, EventType) else event_type
            
            # Wrap callback with priority info
            callback_wrapper = (callback, priority)
            self._subscribers[event_key].append(callback_wrapper)
            
            # Sort by priority (descending)
            self._subscribers[event_key].sort(key=lambda x: x[1], reverse=True)
            
            self._stats["total_subscribers"] += 1
            subscription_id = f"{event_key}:{callback.__name__}:{len(self._subscribers[event_key])}"
            
            logger.debug(f"Subscribed to {event_key}: {callback.__name__} (priority: {priority})")
            return subscription_id
    
    def unsubscribe(self, event_type: EventType, callback: Callable) -> bool:
        """Unsubscribe from an event type.
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: The callback function to remove
            
        Returns:
            True if successfully unsubscribed, False if not found
        """
        with self._lock:
            event_key = event_type.value if isinstance(event_type, EventType) else event_type
            
            if event_key not in self._subscribers:
                return False
            
            # Find and remove the callback wrapper
            for i, (cb, _) in enumerate(self._subscribers[event_key]):
                if cb == callback:
                    self._subscribers[event_key].pop(i)
                    self._stats["total_subscribers"] -= 1
                    logger.debug(f"Unsubscribed from {event_key}: {callback.__name__}")
                    return True
            
            return False
    
    def emit(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> Event:
        """Emit an event to all subscribers.
        
        Args:
            event_type: Type of event to emit
            data: Event data payload
            source: Source of the event
            
        Returns:
            The emitted Event object
        """
        if data is None:
            data = {}
        
        # Create event
        event = Event(
            event_type=event_type,
            data=data,
            source=source,
        )
        
        # Add to history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._stats["total_events"] += 1
        
        # Log event if enabled
        if self._enable_logging:
            logger.info(f"Event emitted: {event_type.value} from {source}")
        
        # Call all subscribers
        event_key = event_type.value
        subscribers = self._subscribers.get(event_key, [])
        
        for callback, _ in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(
                    f"Error in subscriber {callback.__name__} for {event_key}: {e}",
                    exc_info=True
                )
        
        return event
    
    def emit_async(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> threading.Thread:
        """Emit an event asynchronously in a separate thread.
        
        Args:
            event_type: Type of event to emit
            data: Event data payload
            source: Source of the event
            
        Returns:
            Thread object that can be joined
        """
        thread = threading.Thread(
            target=self.emit,
            args=(event_type, data, source),
            daemon=True,
        )
        thread.start()
        return thread
    
    def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get event history.
        
        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of events
        """
        with self._lock:
            history = self._history.copy()
        
        if event_type:
            event_key = event_type.value if isinstance(event_type, EventType) else event_type
            history = [e for e in history if e.event_type.value == event_key]
        
        return history[-limit:]
    
    def clear_history(self):
        """Clear event history."""
        with self._lock:
            self._history.clear()
        logger.info("Event history cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            return {
                "total_events": self._stats["total_events"],
                "total_subscribers": self._stats["total_subscribers"],
                "active_subscriptions": len(self._subscribers),
                "history_size": len(self._history),
                "subscribers_by_type": {k: len(v) for k, v in self._subscribers.items()},
            }
    
    def get_subscribers(self, event_type: EventType) -> List[str]:
        """Get list of subscribers for an event type.
        
        Args:
            event_type: Event type to query
            
        Returns:
            List of subscriber names
        """
        event_key = event_type.value if isinstance(event_type, EventType) else event_type
        return [cb[0].__name__ for cb in self._subscribers.get(event_key, [])]
    
    def clear_subscribers(self, event_type: Optional[EventType] = None):
        """Clear subscribers for an event type (or all if not specified).
        
        Args:
            event_type: Optional event type to clear; if None, clears all
        """
        with self._lock:
            if event_type:
                event_key = event_type.value if isinstance(event_type, EventType) else event_type
                if event_key in self._subscribers:
                    count = len(self._subscribers[event_key])
                    del self._subscribers[event_key]
                    self._stats["total_subscribers"] -= count
                    logger.info(f"Cleared {count} subscribers for {event_key}")
            else:
                count = self._stats["total_subscribers"]
                self._subscribers.clear()
                self._stats["total_subscribers"] = 0
                logger.info(f"Cleared all {count} subscribers")


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus instance.
    
    Returns:
        Global EventBus instance
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def emit_event(
    event_type: EventType,
    data: Optional[Dict[str, Any]] = None,
    source: str = "system",
) -> Event:
    """Convenience function to emit an event via the global bus.
    
    Args:
        event_type: Type of event to emit
        data: Event data payload
        source: Source of the event
        
    Returns:
        The emitted Event object
    """
    return get_event_bus().emit(event_type, data, source)


def subscribe_to_event(
    event_type: EventType,
    callback: Callable,
    priority: int = 0,
) -> str:
    """Convenience function to subscribe via the global bus.
    
    Args:
        event_type: Type of event to subscribe to
        callback: Function to call when event is emitted
        priority: Priority level (higher = called first)
        
    Returns:
        Subscription ID
    """
    return get_event_bus().subscribe(event_type, callback, priority)


if __name__ == "__main__":
    # Test event bus
    logging.basicConfig(level=logging.DEBUG)
    
    bus = EventBus()
    
    def on_vpn_connected(event: Event):
        print(f"VPN Connected! Data: {event.data}")
    
    def on_metrics_updated(event: Event):
        print(f"Metrics Updated: {event.data}")
    
    # Subscribe
    bus.subscribe(EventType.VPN_CONNECTED, on_vpn_connected)
    bus.subscribe(EventType.METRICS_UPDATED, on_metrics_updated)
    
    # Emit events
    bus.emit(EventType.VPN_CONNECTED, {"endpoint": "10.0.0.1", "latency_ms": 25})
    bus.emit(EventType.METRICS_UPDATED, {"latency_ms": 25, "jitter_ms": 2.5})
    
    # Print stats
    print(f"Stats: {bus.get_stats()}")
