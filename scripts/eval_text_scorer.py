import json, os, sys, torch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transformers import BertTokenizer, BertForSequenceClassification
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import numpy as np
import glob

MODEL_DIR = "saved_model/bert_text_scorer"

def trace_to_text(transcript):
    parts = [f"{m['role']}: {m['content']}" for m in transcript]
    return " | ".join(parts)

def main():
    # Load model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = BertForSequenceClassification.from_pretrained(MODEL_DIR)
    tokenizer = BertTokenizer.from_pretrained(MODEL_DIR)
    model.to(device)
    model.eval()
    print(f"Model loaded on {device}")

    # Collect all test traces
    texts, scores = [], []
    for f in glob.glob("runs/*/dialogue_*_trace.json"):
        with open(f, encoding="utf-8") as fh:
            trace = json.load(fh)
        text = trace_to_text(trace["transcript"])
        if not text.strip():
            continue
        texts.append(text)
        scores.append(0.0)  # placeholder if no label available

    # Predict
    preds = []
    with torch.no_grad():
        for text in texts:
            enc = tokenizer(text, max_length=512, truncation=True,
                          padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            out = model(**enc)
            preds.append(out.logits.item())

    preds = np.array(preds)
    print(f"Evaluated {len(preds)} dialogues")
    print(f"  Mean score: {preds.mean():.2f}")
    print(f"  Std:        {preds.std():.2f}")
    print(f"  Min:        {preds.min():.2f}")
    print(f"  Max:        {preds.max():.2f}")

    # Save results
    results = []
    for i, (text, pred) in enumerate(zip(texts, preds)):
        results.append({"text": text[:100], "score": round(float(pred), 2)})
    out = "database/training/bert_predictions.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {out}")

if __name__ == "__main__":
    main()
