from pathlib import Path

from tcfactory.config import load_factory_config
from tcfactory.queue import claim_next, enqueue_task


def test_enqueue_and_claim(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "config").mkdir()
    source_root = Path(__file__).resolve().parents[1]
    config_text = (source_root / "config/factory.yaml").read_text(encoding="utf-8")
    (repo / "config/factory.yaml").write_text(config_text, encoding="utf-8")
    config = load_factory_config(repo / "config/factory.yaml")
    source = source_root / "tasks/DEMO-001.yaml"
    destination = enqueue_task(repo_root=repo, config=config, source=source)
    assert destination.exists()
    claimed = claim_next(repo, config)
    assert claimed.parent.name == "running"
    assert claimed.name == "DEMO-001.yaml"
