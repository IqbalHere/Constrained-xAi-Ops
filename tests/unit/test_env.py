"""Unit tests for environment verification."""

import json
from pathlib import Path
from scripts.verify_env import audit_environment


def test_audit_environment_structure():
    report = audit_environment()
    assert report["status"] == "PASS"
    assert "python_version" in report
    assert "hardware" in report
    assert "packages" in report
    assert isinstance(report["packages"], dict)
    assert report["hardware"]["cpu_cores_logical"] is not None
    assert report["hardware"]["cpu_cores_logical"] > 0


def test_verify_env_file_generation(tmp_path, monkeypatch):
    from scripts.verify_env import main

    # Redirect working dir or output path
    test_artifacts = tmp_path / "artifacts" / "logs"
    test_artifacts.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(tmp_path)
    main()

    out_file = test_artifacts / "env_report.json"
    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["status"] == "PASS"
    assert len(data["packages"]) > 0
