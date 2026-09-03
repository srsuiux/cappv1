import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FileState:
    filename: str
    status: str = "in_progress"  # "in_progress" | "complete"
    completed_slide_indices: list[int] = field(default_factory=list)
    caption_cache: dict[str, str] = field(default_factory=dict)  # image hash -> caption

    def is_slide_done(self, slide_index: int) -> bool:
        return slide_index in self.completed_slide_indices

    def mark_slide_done(self, slide_index: int) -> None:
        if slide_index not in self.completed_slide_indices:
            self.completed_slide_indices.append(slide_index)


def _state_path(state_dir: Path, filename: str) -> Path:
    return state_dir / f"{filename}.json"


def load_state(state_dir: Path, filename: str) -> FileState:
    path = _state_path(state_dir, filename)
    if not path.exists():
        return FileState(filename=filename)
    data = json.loads(path.read_text())
    return FileState(**data)


def save_state(state_dir: Path, state: FileState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(state_dir, state.filename)
    path.write_text(json.dumps(asdict(state), indent=2))
