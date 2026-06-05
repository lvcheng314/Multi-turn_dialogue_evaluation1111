"""
Step 1: Prepare labeled text data for BERT training.
Extracts dialogues, calls _score_with_llm to generate 0-20 labels.
"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dialogue_eval.config import get_settings
from dialogue_eval.schemas import DialogueTrace, ScoringConfig
from dialogue_eval.scorer.text_judge import TextJudgeScorer
from tqdm import tqdm

OUTPUT = "database/training/text_data.jsonl"
MAX_SAMPLES = 200

def collect_traces():
    traces = []
    for f in glob.glob("database/dialogues/*.json"):
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else [data]
        for item in items:
            traces.append(DialogueTrace(**item))
    for f in glob.glob("runs/*/dialogue_*_trace.json"):
        with open(f, encoding="utf-8") as fh:
            traces.append(DialogueTrace(**json.load(fh)))
    return traces

def trace_to_text(trace):
    return " | ".join(f"{m.role}: {m.content}" for m in trace.transcript)

def main():
    os.makedirs("database/training", exist_ok=True)
    traces = collect_traces()
    print(f"Total traces: {len(traces)}")

    settings = get_settings()
    scorer = TextJudgeScorer(settings)
    config = ScoringConfig(enable_llm_judge=True)

    records = []
    for trace in tqdm(traces[:MAX_SAMPLES], desc="LLM scoring"):
        text = trace_to_text(trace)
        if not text.strip():
            continue
        try:
            score, evidence = scorer.score(None, trace, config)
        except Exception as e:
            print(f"SKIP {trace.dialogue_id}: {e}")
            continue
        records.append({"text": text, "score": score, "dialogue_id": trace.dialogue_id})

    config_rules = ScoringConfig(enable_llm_judge=False)
    for trace in traces[:MAX_SAMPLES]:
        text = trace_to_text(trace)
        if not text.strip() or any(r["dialogue_id"] == trace.dialogue_id for r in records):
            continue
        score, _ = scorer.score(None, trace, config_rules)
        records.append({"text": text, "score": score, "dialogue_id": trace.dialogue_id})

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for r in records:
            json.dump(r, f, ensure_ascii=False)
            f.write("\n")
    print(f"Saved {len(records)} records to {OUTPUT}")
    print(f"  LLM-labeled: {sum(1 for r in records if r.get('dialogue_id','') != 'rule')}")
    print(f"  Rule-labeled: {sum(1 for r in records if r.get('dialogue_id','') == 'rule')}")

if __name__ == "__main__":
    main()
