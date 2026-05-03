"""Edge class for connections between warehouse nodes."""

from enum import Enum


class TransferMode(Enum):
    PER_PALLET = "per_pallet"
    BATCH = "batch"


class Edge:
    def __init__(
        self,
        from_node,
        to_node,
        transfer_mode: TransferMode,
        transfer_time: float,
        batch_size: int = 1,
        name: str | None = None,
    ):
        self.from_node = from_node
        self.to_node = to_node
        self.transfer_mode = transfer_mode
        self.transfer_time = transfer_time
        self.batch_size = batch_size

        if transfer_mode == TransferMode.BATCH and batch_size < 1:
            raise ValueError("batch_size must be >= 1 for batch mode")

        node_name_from = getattr(from_node, 'node_name', None) or from_node.name
        node_name_to = getattr(to_node, 'node_name', None) or to_node.name
        self.name = name or f"{node_name_from} -> {node_name_to}"

    def transfer_duration(self, num_pallets: int) -> float:
        if self.transfer_mode == TransferMode.PER_PALLET:
            return num_pallets * self.transfer_time
        else:
            num_batches = (num_pallets + self.batch_size - 1) // self.batch_size
            return num_batches * self.transfer_time

    def max_pallets_per_transfer(self) -> int:
        if self.transfer_mode == TransferMode.PER_PALLET:
            return 1
        return self.batch_size

    def __repr__(self) -> str:
        return (
            f"Edge({self.name}, mode={self.transfer_mode.value}, "
            f"transfer_time={self.transfer_time}, batch_size={self.batch_size})"
        )
