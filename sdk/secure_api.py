import logging
import math
import time
from numbers import Real
from typing import Any, Dict, List
from weakref import WeakKeyDictionary


logger = logging.getLogger("NexusSDK")


class SecureMetric:
    """
    Data descriptor used for validated metric storage.

    Values live inside the descriptor rather than the instance dictionary, which
    avoids trivial bypasses such as assigning to a shadow attribute on the
    instance itself.
    """

    def __init__(self, name: str, initial_value: float = 0.0):
        self.label = name
        self.initial_value = float(initial_value)
        self.public_name = name
        self._values = WeakKeyDictionary()  # type: WeakKeyDictionary

    def __set_name__(self, owner: type, name: str) -> None:
        self.public_name = name

    def __get__(self, instance: Any, owner: type) -> Any:
        if instance is None:
            return self

        value = self._values.get(instance, self.initial_value)
        self._record_event(instance, "get", value)
        return value

    def __set__(self, instance: Any, value: Any) -> None:
        validated = self._validate(value)
        self._values[instance] = validated
        self._record_event(instance, "set", validated)

    def __delete__(self, instance: Any) -> None:
        raise AttributeError("Metric '%s' cannot be deleted." % self.public_name)

    def _validate(self, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("Metric '%s' must be numeric." % self.public_name)

        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("Metric '%s' must be finite." % self.public_name)
        if numeric < 0:
            raise ValueError("Metric '%s' cannot be negative." % self.public_name)
        return numeric

    def _record_event(self, instance: Any, action: str, value: float) -> None:
        if not hasattr(instance, "_audit_log"):
            instance._audit_log = []  # type: ignore[attr-defined]
        instance._audit_log.append(  # type: ignore[attr-defined]
            {"metric": self.public_name, "action": action, "value": value}
        )
        logger.debug("[AUDIT] %s %s=%s", action, self.public_name, value)


class AgentTelemetry:
    """Descriptor-backed telemetry container used by the sandbox demo."""

    cpu_usage = SecureMetric("cpu_usage")
    memory_mb = SecureMetric("memory_mb")
    execution_time = SecureMetric("execution_time")

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.start_time = time.monotonic()
        self._audit_log = []  # type: List[Dict[str, Any]]

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def sync(self) -> Dict[str, Any]:
        """Update derived metrics and return a serializable snapshot."""
        self.execution_time = time.monotonic() - self.start_time
        snapshot = {
            "agent_id": self.agent_id,
            "cpu_usage": self.cpu_usage,
            "memory_mb": self.memory_mb,
            "execution_time": self.execution_time,
        }
        logger.info("Telemetry synced for agent %s", self.agent_id)
        return snapshot


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    telemetry = AgentTelemetry("Nexus-Alpha-1")
    telemetry.cpu_usage = 45.5
    telemetry.memory_mb = 1024
    print(telemetry.sync())
