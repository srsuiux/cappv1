from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """The one folder cappv1 reads and writes. Nothing outside it is touched."""

    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def state_dir(self) -> Path:
        return self.root / ".state"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def env_path(self) -> Path:
        return self.root / ".env"

    def ensure(self) -> None:
        for d in (self.input_dir, self.output_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)


def default_workspace() -> Workspace:
    from cappv1.config import ROOT

    return Workspace(ROOT)
