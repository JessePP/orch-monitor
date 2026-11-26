"""Most miedzy watkiem harmonogramu a watkiem GUI."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from orch_monitor.refresh.snapshot import Snapshot


class SnapshotBridge(QObject):
    """Callback wolany z dowolnego watku emituje sygnal dostarczany w watku GUI (queued)."""

    snapshot_ready = Signal(object)

    def publish(self, snapshot: Snapshot) -> None:
        self.snapshot_ready.emit(snapshot)
