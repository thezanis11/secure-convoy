import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from secure_convoy.report import build_report

out = ROOT/'reports'
build_report(pd.read_csv(out/'trials.csv'), pd.read_csv(out/'summary.csv'),
             json.loads((out/'experiment.json').read_text(encoding='utf-8')), out)
