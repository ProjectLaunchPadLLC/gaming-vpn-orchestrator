"""VPN Service for Gaming VPN Orchestrator.

High-level interface to WireGuard VPN management:
- Connect/disconnect VPN
- Query VPN status (endpoint, peers, throughput)
- Adjust MTU dynamically
- Manage WireGuard configurations
- Monitor handshakes and connection health

Emits VPN_CONNECTED, VPN_DISCONNECTED, VPN_ERROR events to event bus.
All operations thread-safe and event-driven.

Example usage:

    vpn = VPNService()
    vpn.connect()  # Emits VPN_CONNECTED event
    
    status = vpn.get_status()
    print(f"Connected to {status.endpoint}")
    
    vpn.set_mtu(1400)  # Dynamic MTU adjustment
    vpn.disconnect()   # Emits VPN_DISCONNECTED event
"""

import subprocess
import threading
import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services.event_bus import get_event_bus, EventType

logger = logging.getLogger(__name__)


@dataclass
class WireGuardPeer:
    """Represents a WireGuard peer."""
    public_key: str
    endpoint: Optional[str]
    allowed_ips: str
    latest_handshake: Optional[str]
    transfer_rx: int  # Bytes received
    transfer_tx: int  # Bytes sent
    persistent_keepalive: Optional[int]


@dataclass
class VPNStatus:
    """Current VPN connection status."""
    state: str  # 'connected', 'disconnected', 'error'
    interface: str
    endpoint: Optional[str]
    public_key: Optional[str]
    listen_port: Optional[int]
    mtu_size: int
    peers: List[WireGuardPeer]
    total_transfer_rx: int
    total_transfer_tx: int
    last_handshake: Optional[str]
    peer_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary."""
        return {
            "state": self.state,
            "interface": self.interface,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "listen_port": self.listen_port,
            "mtu_size": self.mtu_size,
            "peer_count": self.peer_count,
            "total_transfer_rx": self.total_transfer_rx,
            "total_transfer_tx": self.total_transfer_tx,
            "last_handshake": self.last_handshake,
        }


class VPNService:
    """Manages WireGuard VPN operations.
    
    Provides high-level interface to:
    - Connect/disconnect VPN
    - Query connection status
    - Adjust MTU
    - Monitor peer health
    - Manage configurations
    
    All operations are thread-safe and emit events to event bus.
    """
    
    def __init__(
        self,
        interface: str = "wg0",
        config_dir: str = "/etc/wireguard",
        default_mtu: int = 1420,
    ):
        """Initialize VPN service.
        
        Args:
            interface: WireGuard interface name (e.g., 'wg0')
            config_dir: Directory containing WireGuard configs
            default_mtu: Default MTU size
        """
        self.interface = interface
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / f"{interface}.conf"
        self.default_mtu = default_mtu
        
        self._state = "disconnected"
        self._lock = threading.RLock()
        self._last_status: Optional[VPNStatus] = None
        self.event_bus = get_event_bus()
        
        logger.info(f"VPN service initialized (interface: {interface})")
    
    def connect(self) -> bool:
        """Establish VPN connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            try:
                if self._state == "connected":
                    logger.warning(f"VPN already connected on {self.interface}")
                    return True
                
                logger.info(f"Connecting VPN on {self.interface}")
                
                result = subprocess.run(
                    ["sudo", "wg-quick", "up", self.interface],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    self._state = "connected"
                    status = self.get_status()
                    
                    # Emit event
                    self.event_bus.emit(
                        EventType.VPN_CONNECTED,
                        status.to_dict(),
                        source="vpn_service",
                    )
                    
                    logger.info(f"VPN connected on {self.interface}")
                    return True
                else:
                    logger.error(f"VPN connection failed: {result.stderr}")
                    self._state = "error"
                    self.event_bus.emit(
                        EventType.VPN_ERROR,
                        {"reason": "connection_failed", "error": result.stderr},
                        source="vpn_service",
                    )
                    return False
            
            except subprocess.TimeoutExpired:
                logger.error(f"VPN connection timeout on {self.interface}")
                self._state = "error"
                self.event_bus.emit(
                    EventType.VPN_ERROR,
                    {"reason": "connection_timeout"},
                    source="vpn_service",
                )
                return False
            
            except Exception as e:
                logger.error(f"VPN connection error: {e}", exc_info=True)
                self._state = "error"
                self.event_bus.emit(
                    EventType.VPN_ERROR,
                    {"reason": "connection_error", "error": str(e)},
                    source="vpn_service",
                )
                return False
    
    def disconnect(self) -> bool:
        """Terminate VPN connection.
        
        Returns:
            True if disconnection successful, False otherwise
        """
        with self._lock:
            try:
                if self._state == "disconnected":
                    logger.warning(f"VPN already disconnected on {self.interface}")
                    return True
                
                logger.info(f"Disconnecting VPN on {self.interface}")
                
                result = subprocess.run(
                    ["sudo", "wg-quick", "down", self.interface],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                
                if result.returncode == 0:
                    self._state = "disconnected"
                    
                    # Emit event
                    self.event_bus.emit(
                        EventType.VPN_DISCONNECTED,
                        {"interface": self.interface},
                        source="vpn_service",
                    )
                    
                    logger.info(f"VPN disconnected on {self.interface}")
                    return True
                else:
                    logger.error(f"VPN disconnection failed: {result.stderr}")
                    self._state = "error"
                    self.event_bus.emit(
                        EventType.VPN_ERROR,
                        {"reason": "disconnection_failed", "error": result.stderr},
                        source="vpn_service",
                    )
                    return False
            
            except subprocess.TimeoutExpired:
                logger.error(f"VPN disconnection timeout on {self.interface}")
                self._state = "error"
                self.event_bus.emit(
                    EventType.VPN_ERROR,
                    {"reason": "disconnection_timeout"},
                    source="vpn_service",
                )
                return False
            
            except Exception as e:
                logger.error(f"VPN disconnection error: {e}", exc_info=True)
                self._state = "error"
                self.event_bus.emit(
                    EventType.VPN_ERROR,
                    {"reason": "disconnection_error", "error": str(e)},
                    source="vpn_service",
                )
                return False
    
    def get_status(self) -> VPNStatus:
        """Get current VPN connection status.
        
        Returns:
            VPNStatus object with current connection details
        """
        with self._lock:
            try:
                result = subprocess.run(
                    ["sudo", "wg", "show", self.interface],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                
                if result.returncode == 0:
                    status = self._parse_wg_output(result.stdout)
                    self._last_status = status
                    return status
                else:
                    # VPN not connected
                    return VPNStatus(
                        state="disconnected",
                        interface=self.interface,
                        endpoint=None,
                        public_key=None,
                        listen_port=None,
                        mtu_size=self._get_mtu(),
                        peers=[],
                        total_transfer_rx=0,
                        total_transfer_tx=0,
                        last_handshake=None,
                        peer_count=0,
                    )
            
            except Exception as e:
                logger.error(f"Failed to get VPN status: {e}", exc_info=True)
                return VPNStatus(
                    state="error",
                    interface=self.interface,
                    endpoint=None,
                    public_key=None,
                    listen_port=None,
                    mtu_size=self._get_mtu(),
                    peers=[],
                    total_transfer_rx=0,
                    total_transfer_tx=0,
                    last_handshake=None,
                    peer_count=0,
                )
    
    def _parse_wg_output(self, output: str) -> VPNStatus:
        """Parse output from 'wg show' command.
        
        Args:
            output: Raw output from wg show command
            
        Returns:
            Parsed VPNStatus object
        """
        lines = output.strip().split("\n")
        
        endpoint = None
        public_key = None
        listen_port = None
        peers: List[WireGuardPeer] = []
        total_transfer_rx = 0
        total_transfer_tx = 0
        last_handshake = None
        
        current_peer = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Interface line
            if line.startswith("interface:"):
                # interface: wg0
                pass
            
            # Listen port
            elif "listen port:" in line.lower():
                try:
                    listen_port = int(line.split()[-1])
                except ValueError:
                    pass
            
            # Public key (interface key)
            elif line.startswith("public key:"):
                public_key = line.split()[-1]
            
            # Peer line
            elif line.startswith("peer:"):
                peer_key = line.split()[-1]
                current_peer = {
                    "public_key": peer_key,
                    "endpoint": None,
                    "allowed_ips": "",
                    "latest_handshake": None,
                    "transfer_rx": 0,
                    "transfer_tx": 0,
                    "persistent_keepalive": None,
                }
                peers.append(current_peer)
            
            # Endpoint
            elif "endpoint:" in line.lower() and current_peer:
                parts = line.split()
                if len(parts) >= 2:
                    endpoint = parts[1]
                    current_peer["endpoint"] = endpoint
            
            # Allowed IPs
            elif "allowed ips:" in line.lower() and current_peer:
                ips = line.split(":", 1)[1].strip()
                current_peer["allowed_ips"] = ips
            
            # Latest handshake
            elif "latest handshake:" in line.lower() and current_peer:
                timestamp = line.split(":", 1)[1].strip()
                current_peer["latest_handshake"] = timestamp
                last_handshake = timestamp
            
            # Transfer
            elif "transfer:" in line.lower() and current_peer:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        current_peer["transfer_rx"] = int(parts[1])
                        current_peer["transfer_tx"] = int(parts[3])
                        total_transfer_rx += current_peer["transfer_rx"]
                        total_transfer_tx += current_peer["transfer_tx"]
                    except ValueError:
                        pass
            
            # Persistent keepalive
            elif "persistent keepalive:" in line.lower() and current_peer:
                try:
                    keepalive = int(line.split()[-2])
                    current_peer["persistent_keepalive"] = keepalive
                except ValueError:
                    pass
        
        # Convert peer dicts to WireGuardPeer objects
        wg_peers = [
            WireGuardPeer(
                public_key=p["public_key"],
                endpoint=p["endpoint"],
                allowed_ips=p["allowed_ips"],
                latest_handshake=p["latest_handshake"],
                transfer_rx=p["transfer_rx"],
                transfer_tx=p["transfer_tx"],
                persistent_keepalive=p["persistent_keepalive"],
            )
            for p in peers
        ]
        
        return VPNStatus(
            state="connected" if wg_peers else "disconnected",
            interface=self.interface,
            endpoint=endpoint,
            public_key=public_key,
            listen_port=listen_port,
            mtu_size=self._get_mtu(),
            peers=wg_peers,
            total_transfer_rx=total_transfer_rx,
            total_transfer_tx=total_transfer_tx,
            last_handshake=last_handshake,
            peer_count=len(wg_peers),
        )
    
    def set_mtu(self, mtu: int) -> bool:
        """Set MTU size for VPN interface.
        
        Args:
            mtu: New MTU size in bytes
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                logger.info(f"Setting MTU to {mtu} on {self.interface}")
                
                result = subprocess.run(
                    ["sudo", "ip", "link", "set", "mtu", str(mtu), "dev", self.interface],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                
                if result.returncode == 0:
                    logger.info(f"MTU set to {mtu} on {self.interface}")
                    
                    # Emit event
                    self.event_bus.emit(
                        EventType.VPN_STATUS_CHANGED,
                        {"mtu_size": mtu, "interface": self.interface},
                        source="vpn_service",
                    )
                    
                    return True
                else:
                    logger.error(f"Failed to set MTU: {result.stderr}")
                    return False
            
            except Exception as e:
                logger.error(f"MTU setting error: {e}", exc_info=True)
                return False
    
    def _get_mtu(self) -> int:
        """Get current MTU size for VPN interface.
        
        Returns:
            MTU size in bytes (default: 1420)
        """
        try:
            result = subprocess.run(
                ["ip", "link", "show", self.interface],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            match = re.search(r"mtu\s+(\d+)", result.stdout)
            if match:
                return int(match.group(1))
            
            return self.default_mtu
        except Exception as e:
            logger.debug(f"MTU lookup error: {e}")
            return self.default_mtu
    
    def is_connected(self) -> bool:
        """Check if VPN is currently connected.
        
        Returns:
            True if connected, False otherwise
        """
        with self._lock:
            return self._state == "connected"
    
    def get_state(self) -> str:
        """Get current VPN state.
        
        Returns:
            State string: 'connected', 'disconnected', or 'error'
        """
        with self._lock:
            return self._state
    
    def get_last_status(self) -> Optional[VPNStatus]:
        """Get the last queried VPN status.
        
        Returns:
            Last VPNStatus or None if not yet queried
        """
        with self._lock:
            return self._last_status


# Global VPN service instance
_vpn_service: Optional[VPNService] = None


def get_vpn_service() -> VPNService:
    """Get or create the global VPN service instance.
    
    Returns:
        Global VPNService instance
    """
    global _vpn_service
    if _vpn_service is None:
        _vpn_service = VPNService()
    return _vpn_service


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    vpn = VPNService()
    
    def on_vpn_connected(event):
        print(f"VPN Connected: {event.data}")
    
    def on_vpn_disconnected(event):
        print(f"VPN Disconnected: {event.data}")
    
    def on_vpn_error(event):
        print(f"VPN Error: {event.data}")
    
    bus = get_event_bus()
    bus.subscribe(EventType.VPN_CONNECTED, on_vpn_connected)
    bus.subscribe(EventType.VPN_DISCONNECTED, on_vpn_disconnected)
    bus.subscribe(EventType.VPN_ERROR, on_vpn_error)
    
    # Connect VPN
    vpn.connect()
    
    # Get status
    status = vpn.get_status()
    print(f"Status: {status}")
    
    # Adjust MTU
    vpn.set_mtu(1400)
    
    # Disconnect VPN
    vpn.disconnect()
