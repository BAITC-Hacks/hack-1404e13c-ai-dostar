"""Usage: python -m app.ml.train (after building real Excel datasets)."""
import json

from app.adapters import load_clean
from app.ml.model import MODEL_PATH, train


def main():
    metadata = train(load_clean())
    print(json.dumps(metadata["evaluation"]["overall"], indent=2))
    print(f"Trained model: {MODEL_PATH}")


if __name__ == "__main__":
    main()
