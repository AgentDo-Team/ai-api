"""Download the official BGE reranker and export a local ONNX INT8 model."""

from __future__ import annotations

import argparse
from pathlib import Path

from sentence_transformers import CrossEncoder, export_dynamic_quantized_onnx_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="BAAI/bge-reranker-v2-m3")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/models/bge-reranker-v2-m3-onnx-int8"),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("evaluation/models/huggingface-cache"),
    )
    parser.add_argument(
        "--quantization",
        choices=["arm64", "avx2", "avx512", "avx512_vnni"],
        default="avx2",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    model = CrossEncoder(
        args.model,
        backend="onnx",
        device="cpu",
        cache_folder=str(args.cache_dir),
        model_kwargs={"export": True},
    )
    export_dynamic_quantized_onnx_model(
        model,
        quantization_config=args.quantization,
        model_name_or_path=str(args.output_dir),
        push_to_hub=False,
        file_suffix=f"qint8_{args.quantization}",
    )
    # The quantization helper writes the ONNX graph only. Keep the official
    # tokenizer/config beside it so the exported directory is self-contained.
    model.tokenizer.save_pretrained(args.output_dir)
    model.config.save_pretrained(args.output_dir)
    print(args.output_dir)


if __name__ == "__main__":
    main()
