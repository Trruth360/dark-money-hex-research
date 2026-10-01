"""Hex integration for the dark money tradecraft pipeline."""

from pathlib import Path

from dark_money_tradecraft_analyzer import DarkMoneyTradecraftAnalyzer


def run_hex_analysis() -> dict:
    analyzer = DarkMoneyTradecraftAnalyzer(base_dir=Path("."))
    return analyzer.run()


if __name__ == "__main__":
    outputs = run_hex_analysis()
    for name, frame in outputs.items():
        print(f"\n{name}\n{frame.head()}")
