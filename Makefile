.PHONY: all test test-fast reproduce audit-provenance audit-citations audit-secrets dashboard api clean

all: test audit-provenance audit-citations audit-secrets

test:
	python -m pytest tests/unit/ tests/regression/ -v

test-fast:
	python -m pytest tests/unit/ -v

reproduce:
	python scripts/reproduce_paper.py

audit-provenance:
	python scripts/verify_paper_provenance.py

audit-citations:
	python scripts/audit_citations_and_claims.py

audit-secrets:
	python scripts/check_no_secrets.py

dashboard:
	streamlit run src/dashboard/app.py

api:
	uvicorn src.dashboard.api:app --host 127.0.0.1 --port 8000 --workers 1

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').glob('.pytest_cache')]"
