"""Print a saved assessment:  python tools/inspect_session.py [path-to-json]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.paths import data_dir

path = Path(sys.argv[1]) if len(sys.argv) > 1 else data_dir() / "latest_assessment.json"
if not path.exists():
    sys.exit(f"Not found: {path}")
d = json.loads(path.read_text(encoding="utf-8"))
print("=" * 72, f"\nAIRA-OA assessment {d.get('assessment_id')}  (app {d.get('version')}, algorithm {d.get('algorithm_version', 'legacy')})\n" + "=" * 72)
q = d.get("assessment_quality", {})
print("Overall quality:", q.get("overall_status"))
for k, v in q.get("by_test", {}).items():
    print(f"  {k:<13} {v.get('status'):<8} {'; '.join(v.get('reasons', [])) or 'OK'}")
print("\nFEATURES")
for k, v in d.get("unified_feature_vector", {}).items():
    print(f"  {k:<48} {v}")
