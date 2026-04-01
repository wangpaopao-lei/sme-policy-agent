"""参数调优框架测试"""

import os
import json
import tempfile

from unittest.mock import MagicMock, patch

import pytest

from evaluation.tuning import (
    load_eval_set,
    save_experiment,
    print_comparison_table,
)


class TestLoadEvalSet:
    def test_loads_valid_json(self):
        data = load_eval_set()
        assert isinstance(data, list)
        assert len(data) >= 100

    def test_all_items_have_required_fields(self):
        data = load_eval_set()
        for item in data:
            assert "id" in item
            assert "question" in item
            assert "expected_sources" in item
            assert "category" in item


class TestSaveExperiment:
    def test_saves_json_file(self):
        results = [
            {"value": 60, "recall_at_k": 0.95, "mrr": 0.90, "time_sec": 1.5, "failures": 2},
            {"value": 80, "recall_at_k": 0.92, "mrr": 0.88, "time_sec": 1.4, "failures": 3},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_experiment("rrf_k", results, output_dir=tmpdir)
            assert os.path.exists(path)

            with open(path) as f:
                report = json.load(f)

            assert report["param_name"] == "rrf_k"
            assert len(report["results"]) == 2
            assert report["best"]["value"] == 60  # 最高 recall

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "a", "b")
            path = save_experiment("top_k", [{"value": 5, "recall_at_k": 0.9, "mrr": 0.8, "time_sec": 1, "failures": 1}], output_dir=nested)
            assert os.path.exists(path)


class TestPrintComparison:
    def test_does_not_crash(self):
        """确保打印函数不崩溃"""
        results = [
            {"value": 3, "recall_at_k": 0.85, "mrr": 0.80, "time_sec": 1.0, "failures": 5},
            {"value": 5, "recall_at_k": 0.92, "mrr": 0.88, "time_sec": 1.5, "failures": 3},
            {"value": 10, "recall_at_k": 0.90, "mrr": 0.85, "time_sec": 2.0, "failures": 4},
        ]
        # 不应崩溃
        print_comparison_table("top_k", results)
