"""Main PyQt6 dashboard for Gaming VPN Orchestrator.

Real-time monitoring and control center for:
- VPN connection status and management
- Network metrics (latency, jitter, packet loss, MTU)
- Traffic classification (gaming vs non-gaming)
- AI Worker orchestration and logging
- Profile selection and configuration
"""

import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QPushButton,
    QLabel,
    QStatusBar,
    QMessageBox,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap

logger = logging.getLogger(__name__)


class MetricsUpdater(QThread):
    """Background thread for updating metrics."""

    metrics_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        """Initialize metrics updater thread."""
        super().__init__()
        self.running = True

    def run(self):
        """Run the metrics update loop."""
        try:
            while self.running:
                metrics = {
                    "latency_ms": 0.0,
                    "jitter_ms": 0.0,
                    "packet_loss_pct": 0.0,
                    "mtu_size": 1420,
                    "vpn_state": "disconnected",
                    "timestamp": datetime.now().isoformat(),
                }
                self.metrics_updated.emit(metrics)
                self.msleep(1000)  # Update every second
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        """Stop the metrics updater thread."""
        self.running = False
        self.wait()


class VPNStatusWidget(QWidget):
    """Widget displaying VPN connection status."""

    def __init__(self):
        """Initialize VPN status widget."""
        super().__init__()
        self._init_ui()
        self.is_connected = False

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("VPN Connection Status")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Status indicator
        status_layout = QHBoxLayout()
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: red; font-size: 24px;")
        status_layout.addWidget(self.status_indicator)

        self.status_label = QLabel("Disconnected")
        status_label_font = QFont()
        status_label_font.setPointSize(14)
        status_label_font.setBold(True)
        self.status_label.setFont(status_label_font)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Details grid
        details_layout = QHBoxLayout()

        # Interface info
        iface_layout = QVBoxLayout()
        iface_layout.addWidget(QLabel("Interface:"))
        self.interface_label = QLabel("wg0")
        iface_layout.addWidget(self.interface_label)
        details_layout.addLayout(iface_layout)

        # Endpoint info
        endpoint_layout = QVBoxLayout()
        endpoint_layout.addWidget(QLabel("Endpoint:"))
        self.endpoint_label = QLabel("Not connected")
        endpoint_layout.addWidget(self.endpoint_label)
        details_layout.addLayout(endpoint_layout)

        # Data transferred
        data_layout = QVBoxLayout()
        data_layout.addWidget(QLabel("Data Sent:"))
        self.data_sent_label = QLabel("0 MB")
        data_layout.addWidget(self.data_sent_label)
        details_layout.addLayout(data_layout)

        data_recv_layout = QVBoxLayout()
        data_recv_layout.addWidget(QLabel("Data Received:"))
        self.data_received_label = QLabel("0 MB")
        data_recv_layout.addWidget(self.data_received_label)
        details_layout.addLayout(data_recv_layout)

        layout.addLayout(details_layout)
        layout.addStretch()

    def set_connected(self, connected: bool):
        """Update VPN connection status.

        Args:
            connected: True if connected, False otherwise
        """
        self.is_connected = connected
        if connected:
            self.status_indicator.setStyleSheet("color: green; font-size: 24px;")
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_indicator.setStyleSheet("color: red; font-size: 24px;")
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")


class MetricsWidget(QWidget):
    """Widget displaying real-time network metrics."""

    def __init__(self):
        """Initialize metrics widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Network Metrics")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Latency
        latency_layout = QHBoxLayout()
        latency_layout.addWidget(QLabel("Latency (ms):"))
        self.latency_label = QLabel("-- ms")
        latency_layout.addWidget(self.latency_label)
        self.latency_bar = QProgressBar()
        self.latency_bar.setMaximum(100)
        self.latency_bar.setValue(0)
        latency_layout.addWidget(self.latency_bar)
        layout.addLayout(latency_layout)

        # Jitter
        jitter_layout = QHBoxLayout()
        jitter_layout.addWidget(QLabel("Jitter (ms):"))
        self.jitter_label = QLabel("-- ms")
        jitter_layout.addWidget(self.jitter_label)
        self.jitter_bar = QProgressBar()
        self.jitter_bar.setMaximum(50)
        self.jitter_bar.setValue(0)
        jitter_layout.addWidget(self.jitter_bar)
        layout.addLayout(jitter_layout)

        # Packet Loss
        loss_layout = QHBoxLayout()
        loss_layout.addWidget(QLabel("Packet Loss (%):"))
        self.loss_label = QLabel("-- %")
        loss_layout.addWidget(self.loss_label)
        self.loss_bar = QProgressBar()
        self.loss_bar.setMaximum(10)
        self.loss_bar.setValue(0)
        loss_layout.addWidget(self.loss_bar)
        layout.addLayout(loss_layout)

        # MTU
        mtu_layout = QHBoxLayout()
        mtu_layout.addWidget(QLabel("MTU (bytes):"))
        self.mtu_label = QLabel("1420")
        mtu_layout.addWidget(self.mtu_label)
        layout.addLayout(mtu_layout)

        # Performance rating
        rating_layout = QHBoxLayout()
        rating_layout.addWidget(QLabel("Performance Rating:"))
        self.rating_label = QLabel("Excellent")
        rating_font = QFont()
        rating_font.setBold(True)
        self.rating_label.setFont(rating_font)
        self.rating_label.setStyleSheet("color: green;")
        rating_layout.addWidget(self.rating_label)
        layout.addLayout(rating_layout)

        layout.addStretch()

    def update_metrics(self, metrics: Dict[str, Any]):
        """Update displayed metrics.

        Args:
            metrics: Dictionary with metric values
        """
        latency = metrics.get("latency_ms", 0)
        jitter = metrics.get("jitter_ms", 0)
        packet_loss = metrics.get("packet_loss_pct", 0)
        mtu = metrics.get("mtu_size", 1420)

        # Update labels
        self.latency_label.setText(f"{latency:.2f} ms")
        self.jitter_label.setText(f"{jitter:.2f} ms")
        self.loss_label.setText(f"{packet_loss:.2f} %")
        self.mtu_label.setText(f"{mtu} bytes")

        # Update progress bars (with scaling)
        self.latency_bar.setValue(min(int(latency), 100))
        self.jitter_bar.setValue(min(int(jitter * 2.5), 50))
        self.loss_bar.setValue(min(int(packet_loss), 10))

        # Update performance rating
        if latency < 30 and jitter < 5 and packet_loss < 0.1:
            self.rating_label.setText("Excellent")
            self.rating_label.setStyleSheet("color: green;")
        elif latency < 50 and jitter < 10 and packet_loss < 0.5:
            self.rating_label.setText("Good")
            self.rating_label.setStyleSheet("color: #90EE90;")
        elif latency < 100 and jitter < 20 and packet_loss < 1.0:
            self.rating_label.setText("Fair")
            self.rating_label.setStyleSheet("color: orange;")
        else:
            self.rating_label.setText("Poor")
            self.rating_label.setStyleSheet("color: red;")


class TrafficWidget(QWidget):
    """Widget displaying traffic classification statistics."""

    def __init__(self):
        """Initialize traffic widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Traffic Classification")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Stats
        stats_layout = QHBoxLayout()

        # Gaming traffic
        gaming_layout = QVBoxLayout()
        gaming_layout.addWidget(QLabel("Gaming Flows:"))
        self.gaming_flows_label = QLabel("0")
        gaming_label_font = QFont()
        gaming_label_font.setPointSize(14)
        gaming_label_font.setBold(True)
        self.gaming_flows_label.setFont(gaming_label_font)
        self.gaming_flows_label.setStyleSheet("color: green;")
        gaming_layout.addWidget(self.gaming_flows_label)
        stats_layout.addLayout(gaming_layout)

        # Non-gaming traffic
        non_gaming_layout = QVBoxLayout()
        non_gaming_layout.addWidget(QLabel("Non-Gaming Flows:"))
        self.non_gaming_flows_label = QLabel("0")
        self.non_gaming_flows_label.setFont(gaming_label_font)
        self.non_gaming_flows_label.setStyleSheet("color: orange;")
        non_gaming_layout.addWidget(self.non_gaming_flows_label)
        stats_layout.addLayout(non_gaming_layout)

        # Unknown traffic
        unknown_layout = QVBoxLayout()
        unknown_layout.addWidget(QLabel("Unknown Flows:"))
        self.unknown_flows_label = QLabel("0")
        self.unknown_flows_label.setFont(gaming_label_font)
        unknown_layout.addWidget(self.unknown_flows_label)
        stats_layout.addLayout(unknown_layout)

        layout.addLayout(stats_layout)

        # Data rates
        rate_layout = QHBoxLayout()
        rate_layout.addWidget(QLabel("Gaming Data Rate:"))
        self.gaming_rate_label = QLabel("0 Mbps")
        rate_layout.addWidget(self.gaming_rate_label)
        layout.addLayout(rate_layout)

        layout.addStretch()

    def update_traffic_stats(self, stats: Dict[str, Any]):
        """Update traffic statistics.

        Args:
            stats: Dictionary with traffic statistics
        """
        self.gaming_flows_label.setText(str(stats.get("gaming_flows", 0)))
        self.non_gaming_flows_label.setText(str(stats.get("non_gaming_flows", 0)))
        self.unknown_flows_label.setText(str(stats.get("unknown_flows", 0)))


class WorkerWidget(QWidget):
    """Widget for AI Worker orchestration and monitoring."""

    def __init__(self):
        """Initialize worker widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("AI Worker Orchestration")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Worker status
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Active Workers:"))
        self.worker_count_label = QLabel("0")
        worker_count_font = QFont()
        worker_count_font.setPointSize(14)
        worker_count_font.setBold(True)
        self.worker_count_label.setFont(worker_count_font)
        status_layout.addWidget(self.worker_count_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Control buttons
        button_layout = QHBoxLayout()
        self.launch_btn = QPushButton("Launch Worker")
        self.launch_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; padding: 8px; border-radius: 4px;"
        )
        button_layout.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("Stop Worker")
        self.stop_btn.setStyleSheet(
            "background-color: #f44336; color: white; padding: 8px; border-radius: 4px;"
        )
        button_layout.addWidget(self.stop_btn)

        self.pause_btn = QPushButton("Pause Worker")
        self.pause_btn.setStyleSheet(
            "background-color: #FF9800; color: white; padding: 8px; border-radius: 4px;"
        )
        button_layout.addWidget(self.pause_btn)

        layout.addLayout(button_layout)

        # Worker log
        layout.addWidget(QLabel("Worker Decisions Log:"))
        from PyQt6.QtWidgets import QTextEdit
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(150)
        self.log_display.setText("No workers running...\n")
        self.log_display.setStyleSheet(
            "background-color: #2d2d2d; color: #00ff00; font-family: Courier;"
        )
        layout.addWidget(self.log_display)

    def add_log_entry(self, message: str):
        """Add a log entry to the display.

        Args:
            message: Log message
        """
        current_text = self.log_display.toPlainText()
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.setText(
            f"{current_text}[{timestamp}] {message}\n"
        )
        # Keep only last 100 lines
        lines = self.log_display.toPlainText().split("\n")
        if len(lines) > 100:
            self.log_display.setText("\n".join(lines[-100:]))


class ProfileWidget(QWidget):
    """Widget for profile selection and management."""

    def __init__(self):
        """Initialize profile widget."""
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Gaming Profiles")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Profile selector
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Select Profile:"))

        from PyQt6.QtWidgets import QComboBox
        self.profile_combo = QComboBox()
        self.profile_combo.addItems([
            "Xbox Cloud Gaming",
            "GeForce Now",
            "PlayStation Cloud",
            "Custom"
        ])
        profile_layout.addWidget(self.profile_combo)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet(
            "background-color: #0d47a1; color: white; padding: 5px; border-radius: 4px;"
        )
        profile_layout.addWidget(self.apply_btn)
        layout.addLayout(profile_layout)

        # Profile info
        layout.addWidget(QLabel("\nProfile Configuration:"))

        info_layout = QVBoxLayout()
        self.profile_info = {
            "name": QLabel("Profile: Xbox Cloud Gaming"),
            "mtu": QLabel("MTU: 1420 bytes"),
            "keepalive": QLabel("Keepalive: 25 seconds"),
            "priority": QLabel("Priority: High"),
        }
        for widget in self.profile_info.values():
            info_layout.addWidget(widget)

        layout.addLayout(info_layout)
        layout.addStretch()


class GamingVPNDashboard(QMainWindow):
    """Main dashboard window for Gaming VPN Orchestrator.

    Provides real-time monitoring and control of:
    - VPN connection status
    - Network metrics (latency, jitter, packet loss, MTU)
    - Traffic classification
    - AI Worker orchestration
    - Profile management
    """

    def __init__(self):
        """Initialize the dashboard."""
        super().__init__()
        self.setWindowTitle("Gaming VPN Orchestrator")
        self.setGeometry(50, 50, 1600, 1000)

        # Apply dark theme
        self.setStyleSheet(self._get_dark_stylesheet())

        # Initialize central widget
        self._init_ui()

        # Start metrics updater thread
        self.metrics_updater = MetricsUpdater()
        self.metrics_updater.metrics_updated.connect(self._on_metrics_updated)
        self.metrics_updater.error_occurred.connect(self._on_updater_error)
        self.metrics_updater.start()

        logger.info("Gaming VPN Dashboard initialized")

    def _init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Title bar
        title = QLabel("Gaming VPN Orchestrator - Cloud Gaming Network Optimization")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setStyleSheet("color: #0d47a1; padding: 10px;")
        title.setFont(title_font)
        main_layout.addWidget(title)

        # Tab widget
        self.tabs = QTabWidget()
        
        # VPN Status Tab
        self.vpn_widget = VPNStatusWidget()
        self.tabs.addTab(self.vpn_widget, "VPN Status")

        # Metrics Tab
        self.metrics_widget = MetricsWidget()
        self.tabs.addTab(self.metrics_widget, "Metrics")

        # Traffic Tab
        self.traffic_widget = TrafficWidget()
        self.tabs.addTab(self.traffic_widget, "Traffic")

        # Workers Tab
        self.worker_widget = WorkerWidget()
        self.tabs.addTab(self.worker_widget, "Workers")

        # Profiles Tab
        self.profile_widget = ProfileWidget()
        self.tabs.addTab(self.profile_widget, "Profiles")

        main_layout.addWidget(self.tabs)

        # Control buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect VPN")
        self.connect_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; padding: 10px; border-radius: 4px; font-weight: bold;"
        )
        self.connect_btn.clicked.connect(self._on_vpn_connect)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect VPN")
        self.disconnect_btn.setStyleSheet(
            "background-color: #f44336; color: white; padding: 10px; border-radius: 4px; font-weight: bold;"
        )
        self.disconnect_btn.clicked.connect(self._on_vpn_disconnect)
        button_layout.addWidget(self.disconnect_btn)

        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # Status bar
        self.statusBar().showMessage("Ready | VPN: Disconnected | Workers: 0")

        # Connect worker buttons
        self.worker_widget.launch_btn.clicked.connect(self._on_launch_worker)
        self.worker_widget.stop_btn.clicked.connect(self._on_stop_worker)
        self.profile_widget.apply_btn.clicked.connect(self._on_apply_profile)

    def _on_vpn_connect(self):
        """Handle VPN connect button click."""
        self.statusBar().showMessage("Connecting VPN...")
        self.vpn_widget.set_connected(True)
        logger.info("VPN connect clicked")
        self.statusBar().showMessage("Ready | VPN: Connected | Workers: 0")

    def _on_vpn_disconnect(self):
        """Handle VPN disconnect button click."""
        self.statusBar().showMessage("Disconnecting VPN...")
        self.vpn_widget.set_connected(False)
        logger.info("VPN disconnect clicked")
        self.statusBar().showMessage("Ready | VPN: Disconnected | Workers: 0")

    def _on_launch_worker(self):
        """Handle launch worker button click."""
        self.worker_widget.add_log_entry("Launching AI Worker...")
        logger.info("Worker launch clicked")

    def _on_stop_worker(self):
        """Handle stop worker button click."""
        self.worker_widget.add_log_entry("Stopping AI Worker...")
        logger.info("Worker stop clicked")

    def _on_apply_profile(self):
        """Handle apply profile button click."""
        profile = self.profile_widget.profile_combo.currentText()
        self.worker_widget.add_log_entry(f"Applied profile: {profile}")
        logger.info(f"Profile applied: {profile}")

    def _on_metrics_updated(self, metrics: Dict[str, Any]):
        """Handle metrics update signal.

        Args:
            metrics: Dictionary with updated metrics
        """
        self.metrics_widget.update_metrics(metrics)

    def _on_updater_error(self, error_msg: str):
        """Handle metrics updater error.

        Args:
            error_msg: Error message
        """
        logger.error(f"Metrics updater error: {error_msg}")

    def closeEvent(self, event):
        """Handle window close event.

        Args:
            event: Close event
        """
        self.metrics_updater.stop()
        logger.info("Dashboard closed")
        event.accept()

    @staticmethod
    def _get_dark_stylesheet() -> str:
        """Get dark theme stylesheet.

        Returns:
            CSS stylesheet string
        """
        return """
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabWidget {
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 8px 20px;
                border: 1px solid #3d3d3d;
            }
            QTabBar::tab:selected {
                background-color: #0d47a1;
                color: #ffffff;
            }
            QPushButton {
                background-color: #0d47a1;
                color: #ffffff;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:pressed {
                background-color: #0d3a8c;
            }
            QLabel {
                color: #ffffff;
            }
            QProgressBar {
                border: 2px solid #3d3d3d;
                border-radius: 4px;
                background-color: #2d2d2d;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
            }
            QComboBox {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QStatusBar {
                background-color: #2d2d2d;
                color: #ffffff;
                border-top: 1px solid #3d3d3d;
            }
        """


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = sys.modules.get("app") or __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication(sys.argv)
    dashboard = GamingVPNDashboard()
    dashboard.show()
    sys.exit(app.exec())
