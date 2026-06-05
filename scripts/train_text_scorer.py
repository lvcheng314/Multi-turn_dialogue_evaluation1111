import json, os, glob, sys, random, argparse
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (BertTokenizer, BertForSequenceClassification, get_linear_schedule_with_warmup)
from sklearn.model_selection import train_test_split
from tqdm import tqdm
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--data", "-d", default="database/training/飞毛腿训练数据.json",
    help="Path to .jsonl training data or directory with .json dialogue files")
parser.add_argument("--output", "-o", default="saved_model/bert_text_scorer",
    help="Directory to save trained model")
parser.add_argument("--epochs", "-e", type=int, default=8, help="Number of epochs")
args = parser.parse_args()

DATA_FILE = args.data
MODEL_DIR = args.output
EPOCHS = args.epochs
def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs("database/training", exist_ok=True)

    os.makedirs("database/training", exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    # Load data
    texts, scores = [], []
    if os.path.isdir(DATA_FILE):
        # Load from directory of .json dialogue files
        from dialogue_eval.schemas import DialogueTrace, ScoringConfig
        from dialogue_eval.scorer.text_judge import TextJudgeScorer
        from dialogue_eval.config import get_settings
        settings = get_settings()
        scorer = TextJudgeScorer(settings)
        for f in glob.glob(os.path.join(DATA_FILE, "*.json")):
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            items = data if isinstance(data, list) else [data]
            for item in items:
                try:
                    trace = DialogueTrace(**item)
                except:
                    continue
                text = " | ".join(f"{m.role}: {m.content}" for m in trace.transcript)
                if not text.strip():
                    continue
                texts.append(text)
                scores.append(0.0)
        print(f"Loaded {len(texts)} dialogues from {DATA_FILE}")
    elif os.path.isfile(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                texts.append(r["text"])
                scores.append(float(r["score"]))
        print(f"Loaded {len(texts)} records from {DATA_FILE}")
    else:
        print(f"Data not found: {DATA_FILE}")
        sys.exit(1)

    if len(texts) < 5:
        print(f"Not enough data ({len(texts)}). Generate labels first with prepare_text_data.py")
        return

    # Split
    train_texts, val_texts, train_scores, val_scores = train_test_split(
        texts, scores, test_size=0.2, random_state=42
    )
    print(f"Train: {len(train_texts)}, Val: {len(val_texts)}")

    # Model
    tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
    model = BertForSequenceClassification.from_pretrained(
        "bert-base-chinese", num_labels=1, problem_type="regression"
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"Device: {device}")

    # DataLoaders
    train_ds = TextScoreDataset(train_texts, train_scores, tokenizer, MAX_LEN)
    val_ds = TextScoreDataset(val_texts, val_scores, tokenizer, MAX_LEN)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)

    # Optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    total_steps = len(train_loader) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=total_steps // 10, num_training_steps=total_steps
    )

    # Training loop
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            total_loss += loss.item()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

        # Validation
        model.eval()
        val_loss, preds, targets = 0, [], []
        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                outputs = model(**batch)
                val_loss += outputs.loss.item()
                preds.extend(outputs.logits.squeeze(-1).cpu().tolist())
                targets.extend(batch["labels"].cpu().tolist())

        mse = np.mean((np.array(preds) - np.array(targets)) ** 2)
        mae = np.mean(np.abs(np.array(preds) - np.array(targets)))
        print(f"  Loss: {total_loss/len(train_loader):.4f}, "
              f"Val Loss: {val_loss/len(val_loader):.4f}, "
              f"MSE: {mse:.4f}, MAE: {mae:.4f}")

    # Save model
    model.save_pretrained(MODEL_DIR)
    tokenizer.save_pretrained(MODEL_DIR)
    print(f"Model saved to {MODEL_DIR}")

if __name__ == "__main__":
    main()
