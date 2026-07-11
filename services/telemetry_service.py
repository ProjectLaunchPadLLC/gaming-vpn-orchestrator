"""Telemetry Service for Gaming VPN Orchestrator.

Collects real-time network metrics from the system:
- Latency (via ping)
- Jitter (standard deviation of latency)
- Packet loss
- MTU size
- VPN throughput (bytes sent/received)
- System resources (CPU, memory)

Runs in background thread and emits METRICS_UPDATED events to event bus.
No UI dependencies—purely data collection.

Example usage:

    telemetry = TelemetryService()
    telemetry.start()
    
    # Events automatically emitted to event bus
    # Subscribe to them in UI:
    bus.subscribe(EventType.METRICS_UPDATED, on_metrics_updated)
"""

import subprocess
import threading
import time
import statistics
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import re
import psutil

from services.event_bus import get_event_bus, EventType

logger = logging.getLogger(__name__)


@dataclass
class LatencySample:
    """Single latency measurement."""
    timestamp: datetime
    latency_ms: float


@dataclass
class MetricsSnapshot:
    """Complete metrics snapshot at a point in time."""
    timestamp: str
    latency_ms: float
    jitter_ms: float
    packet_loss_pct: float
    mtu_size: int
    fragmentation_detected: bool
    vpn_state: str
    vpn_endpoint: Optional[str]
    data_sent_bytes: int
    data_received_bytes: int
    cpu_percent: float
    memory_percent: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event payload."""
        return {
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "mtu_size": self.mtu_size,
            "fragmentation_detected": self.fragmentation_detected,
            "vpn_state": self.vpn_state,
            "vpn_endpoint": self.vpn_endpoint,
            "data_sent_bytes": self.data_sent_bytes,
            "data_received_bytes": self.data_received_bytes,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
        }


class TelemetryService:
    """Collects real-time system metrics via subprocess calls.
    
    Metrics collected:
    - Latency: ICMP ping to configurable targets (default: 8.8.8.8)
    - Jitter: Standard deviation of latency samples
    - Packet Loss: Percentage of lost ICMP packets
    - MTU: Current MTU size on VPN interface
    - VPN State: Connected/disconnected status
    - Throughput: Bytes sent/received on VPN interface
    - System: CPU and memory utilization
    
    Runs in background thread, emits events every interval.
    """
    
    def __init__(
        self,
        collection_interval: float = 1.0,
        target_host: str = "8.8.8.8",
        ping_count: int = 4,
        vpn_interface: str = "wg0",
        sample_window_size: int = 10,
    ):
        """Initialize telemetry service.
        
        Args:
            collection_interval: Seconds between metric collections
            target_host: Host to ping for latency measurement
            ping_count: Number of ping packets per measurement
            vpn_interface: VPN interface to monitor (e.g., 'wg0')
            sample_window_size: Number of samples for jitter calculation
        """
        self.collection_interval = collection_interval
        self.target_host = target_host
        self.ping_count = ping_count
        self.vpn_interface = vpn_interface
        self.sample_window_size = sample_window_size
        
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        
        self.latency_samples: List[LatencySample] = []
        self.last_snapshot: Optional[MetricsSnapshot] = None
        self.event_bus = get_event_bus()
        
        logger.info(
            f"Telemetry service initialized (target: {target_host}, "
            f"interface: {vpn_interface}, interval: {collection_interval}s)"
        )
    
    def start(self) -> bool:
        """Start the telemetry collection thread.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("Telemetry service already running")
            return False
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._collection_loop,
            name="TelemetryService",
            daemon=True,
        )
        self._thread.start()
        logger.info("Telemetry service started")
        return True
    
    def stop(self) -> bool:
        """Stop the telemetry collection thread.
        
        Returns:
            True if stopped successfully, False if not running
        """
        if not self._running:
            return False
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        logger.info("Telemetry service stopped")
        return True
    
    def _collection_loop(self):
        """Main telemetry collection loop (runs in background thread)."""
        try:
            while self._running and not self._stop_event.is_set():
                try:
                    snapshot = self.collect_metrics()
                    self.last_snapshot = snapshot
                    
                    # Emit event to bus
                    self.event_bus.emit(
                        EventType.METRICS_UPDATED,
                        snapshot.to_dict(),
                        source="telemetry_service",
                    )
                    
                    # Check for anomalies
                    self._check_anomalies(snapshot)
                    
                except Exception as e:
                    logger.error(f"Error in metrics collection: {e}", exc_info=True)
                
                # Wait for next collection interval
                self._stop_event.wait(self.collection_interval)
        
        except Exception as e:
            logger.error(f"Telemetry collection loop error: {e}", exc_info=True)
            self._running = False
    
    def collect_metrics(self) -> MetricsSnapshot:
        """Collect a complete metrics snapshot.
        
        Returns:
            MetricsSnapshot with all current metrics
        """
        # Collect latency
        latency_ms = self._measure_latency()
        
        # Track sample for jitter calculation
        if latency_ms > 0:
            self.latency_samples.append(LatencySample(datetime.now(), latency_ms))
            if len(self.latency_samples) > self.sample_window_size:
                self.latency_samples.pop(0)
        
        # Calculate jitter
        jitter_ms = self._calculate_jitter()
        
        # Measure packet loss
        packet_loss_pct = self._measure_packet_loss()
        
        # Get MTU
        mtu_size = self._get_mtu()
        
        # Detect fragmentation
        fragmentation = self._detect_fragmentation()
        
        # Get VPN state
        vpn_state, vpn_endpoint = self._get_vpn_state()
        
        # Get VPN throughput
        data_sent, data_received = self._get_vpn_throughput()
        
        # Get system resources
        cpu_percent, memory_percent = self._get_system_resources()
        
        return MetricsSnapshot(
            timestamp=datetime.now().isoformat(),
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            packet_loss_pct=packet_loss_pct,
            mtu_size=mtu_size,
            fragmentation_detected=fragmentation,
            vpn_state=vpn_state,
            vpn_endpoint=vpn_endpoint,
            data_sent_bytes=data_sent,
            data_received_bytes=data_received,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
        )
    
    def _measure_latency(self) -> float:
        """Measure latency via ICMP ping.
        
        Returns:
            Latency in milliseconds, or 0 if failed
        """
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.target_host],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                # Parse: time=25.3 ms
                match = re.search(r"time=([0-9.]+)\s*ms", result.stdout)
                if match:
                    latency = float(match.group(1))
                    logger.debug(f"Latency: {latency}ms")
                    return latency
            
            return 0.0
        except Exception as e:
            logger.debug(f"Latency measurement error: {e}")
            return 0.0
    
    def _calculate_jitter(self) -> float:
        """Calculate jitter (standard deviation of latency samples).
        
        Returns:
            Jitter in milliseconds
        """
        try:
            if len(self.latency_samples) < 2:
                return 0.0
            
            latencies = [s.latency_ms for s in self.latency_samples]
            jitter = statistics.stdev(latencies)
            logger.debug(f"Jitter: {jitter}ms")
            return jitter
        except Exception as e:
            logger.debug(f"Jitter calculation error: {e}")
            return 0.0
    
    def _measure_packet_loss(self) -> float:
        """Measure packet loss percentage.
        
        Returns:
            Packet loss as percentage (0-100)
        """
        try:
            result = subprocess.run(
                ["ping", "-c", "10", "-W", "2", self.target_host],
                capture_output=True,
                text=True,
                timeout=15,
            )
            
            # Parse: X% packet loss
            match = re.search(r"([0-9.]+)%\s*packet loss", result.stdout)
            if match:
                packet_loss = float(match.group(1))
                logger.debug(f"Packet loss: {packet_loss}%")
                return packet_loss
            
            return 0.0
        except Exception as e:
            logger.debug(f"Packet loss measurement error: {e}")
            return 0.0
    
    def _get_mtu(self) -> int:
        """Get current MTU size on VPN interface.
        
        Returns:
            MTU size in bytes (default: 1420)
        """
        try:
            result = subprocess.run(
                ["ip", "link", "show", self.vpn_interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            match = re.search(r"mtu\s+(\d+)", result.stdout)
            if match:
                mtu = int(match.group(1))
                logger.debug(f"MTU: {mtu}")
                return mtu
            
            return 1420  # Default for WireGuard
        except Exception as e:
            logger.debug(f"MTU lookup error: {e}")
            return 1420
    
    def _detect_fragmentation(self) -> bool:
        """Detect if packets are being fragmented.
        
        Returns:
            True if fragmentation detected, False otherwise
        """
        try:
            result = subprocess.run(
                ["ip", "-s", "link", "show", self.vpn_interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            # Look for dropped or overrun counters
            if any(keyword in result.stdout for keyword in ["dropped", "overrun", "errors"]):
                logger.debug("Fragmentation detected")
                return True
            
            return False
        except Exception as e:
            logger.debug(f"Fragmentation detection error: {e}")
            return False
    
    def _get_vpn_state(self) -> tuple[str, Optional[str]]:
        """Get VPN connection state and endpoint.
        
        Returns:
            Tuple of (state, endpoint) where state is 'connected', 'disconnected', or 'error'
        """
        try:
            result = subprocess.run(
                ["sudo", "wg", "show", self.vpn_interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode == 0:
                # Extract endpoint
                endpoint = None
                for line in result.stdout.split("\n"):
                    if "endpoint" in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            endpoint = parts[1]
                            break
                
                logger.debug(f"VPN state: connected (endpoint: {endpoint})")
                return "connected", endpoint
            else:
                return "disconnected", None
        except Exception as e:
            logger.debug(f"VPN state check error: {e}")
            return "error", None
    
    def _get_vpn_throughput(self) -> tuple[int, int]:
        """Get VPN throughput (bytes sent/received).
        
        Returns:
            Tuple of (bytes_sent, bytes_received)
        """
        try:
            result = subprocess.run(
                ["ip", "-s", "link", "show", self.vpn_interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            lines = result.stdout.split("\n")
            bytes_sent = 0
            bytes_received = 0
            
            for i, line in enumerate(lines):
                if "RX" in line or "TX" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            if "RX" in line:
                                bytes_received = int(parts[1])
                            elif "TX" in line:
                                bytes_sent = int(parts[1])
                        except ValueError:
                            pass
            
            logger.debug(f"Throughput: sent={bytes_sent}, recv={bytes_received}")
            return bytes_sent, bytes_received
        except Exception as e:
            logger.debug(f"Throughput lookup error: {e}")
            return 0, 0
    
    def _get_system_resources(self) -> tuple[float, float]:
        """Get system CPU and memory utilization.
        
        Returns:
            Tuple of (cpu_percent, memory_percent)
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            logger.debug(f"System resources: CPU={cpu_percent}%, Memory={memory_percent}%")
            return cpu_percent, memory_percent
        except Exception as e:
            logger.debug(f"System resources error: {e}")
            return 0.0, 0.0
    
    def _check_anomalies(self, snapshot: MetricsSnapshot):
        """Check for metric anomalies and emit appropriate events.
        
        Args:
            snapshot: Current metrics snapshot
        """
        # Check for latency spike
        if snapshot.latency_ms > 100:  # 100ms threshold
            self.event_bus.emit(
                EventType.LATENCY_SPIKE,
                {"latency_ms": snapshot.latency_ms},
                source="telemetry_service",
            )
        
        # Check for packet loss
        if snapshot.packet_loss_pct > 1.0:  # 1% threshold
            self.event_bus.emit(
                EventType.PACKET_LOSS_DETECTED,
                {"packet_loss_pct": snapshot.packet_loss_pct},
                source="telemetry_service",
            )
        
        # Check for fragmentation
        if snapshot.fragmentation_detected:
            self.event_bus.emit(
                EventType.METRICS_ANOMALY,
                {"reason": "fragmentation_detected", "mtu": snapshot.mtu_size},
                source="telemetry_service",
            )
    
    def get_last_snapshot(self) -> Optional[MetricsSnapshot]:
        """Get the last collected metrics snapshot.
        
        Returns:
            Last MetricsSnapshot or None if not yet collected
        """
        return self.last_snapshot
    
    def is_running(self) -> bool:
        """Check if telemetry service is running.
        
        Returns:
            True if running, False otherwise
        """
        return self._running


# Global telemetry service instance
_telemetry_service: Optional[TelemetryService] = None


def get_telemetry_service() -> TelemetryService:
    """Get or create the global telemetry service instance.
    
    Returns:
        Global TelemetryService instance
    """
    global _telemetry_service
    if _telemetry_service is None:
        _telemetry_service = TelemetryService()
    return _telemetry_service


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    telemetry = TelemetryService()
    
    def on_metrics(event):
        print(f"Metrics: {event.data}")
    
    def on_anomaly(event):
        print(f"Anomaly detected: {event.data}")
    
    bus = get_event_bus()
    bus.subscribe(EventType.METRICS_UPDATED, on_metrics)
    bus.subscribe(EventType.METRICS_ANOMALY, on_anomaly)
    
    telemetry.start()
    
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        telemetry.stop()
