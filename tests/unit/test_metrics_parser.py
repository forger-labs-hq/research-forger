import json
from pathlib import Path

import pytest
import yaml

from researchforge.domain.contract import ContractSpec
from researchforge.execution.metrics import MetricParseError, parse_result_file

CONTRACTS = Path(__file__).parent.parent / "fixtures" / "contracts"


@pytest.fixture
def spec() -> ContractSpec:
    data = yaml.safe_load((CONTRACTS / "example_full.yaml").read_text(encoding="utf-8"))
    return ContractSpec.model_validate(data)


def _write(tmp_path: Path, payload: object) -> Path:
    target = tmp_path / "results.json"
    target.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return target


_VALID = {
    "schema_version": 1,
    "primary_metric": {"name": "quality_score", "value": 0.842},
    "secondary_metrics": {"p95_latency_ms": 188.4, "average_cost_usd": 0.014},
    "sample_count": 1200,
    "seed": 42,
    "metadata": {"dataset_version": "benchmark-v2"},
}


class TestParseResultFile:
    def test_valid_result(self, tmp_path: Path, spec: ContractSpec) -> None:
        result, warnings = parse_result_file(_write(tmp_path, _VALID), spec)

        assert result.primary_metric.value == 0.842
        assert result.secondary_metrics["p95_latency_ms"] == 188.4
        # quality_regression constraint is not reported → warning, not error.
        assert any("quality_regression" in w for w in warnings)

    def test_missing_file_names_expected_path(self, tmp_path: Path, spec: ContractSpec) -> None:
        with pytest.raises(MetricParseError, match="artifacts/results.json"):
            parse_result_file(tmp_path / "results.json", spec)

    def test_invalid_json(self, tmp_path: Path, spec: ContractSpec) -> None:
        with pytest.raises(MetricParseError, match="not valid JSON"):
            parse_result_file(_write(tmp_path, "{broken"), spec)

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_nan_infinity_tokens_rejected(
        self, tmp_path: Path, spec: ContractSpec, token: str
    ) -> None:
        text = (
            '{"schema_version": 1, "primary_metric": {"name": "quality_score", '
            f'"value": {token}}}}}'
        )
        with pytest.raises(MetricParseError):
            parse_result_file(_write(tmp_path, text), spec)

    def test_non_object_rejected(self, tmp_path: Path, spec: ContractSpec) -> None:
        with pytest.raises(MetricParseError, match="JSON object"):
            parse_result_file(_write(tmp_path, [1, 2]), spec)

    def test_wrong_schema_version(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, schema_version=2)
        with pytest.raises(MetricParseError, match="schema_version"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_missing_primary_metric(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = {"schema_version": 1}
        with pytest.raises(MetricParseError, match="primary_metric"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_wrong_metric_name(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, primary_metric={"name": "other", "value": 1.0})
        with pytest.raises(MetricParseError, match="expects 'quality_score'"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_bool_value_rejected(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, primary_metric={"name": "quality_score", "value": True})
        with pytest.raises(MetricParseError, match="number"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_string_secondary_rejected(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, secondary_metrics={"p95_latency_ms": "fast"})
        with pytest.raises(MetricParseError, match="p95_latency_ms"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_unknown_top_level_key_rejected(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, extra_field=1)
        with pytest.raises(MetricParseError, match="extra_field"):
            parse_result_file(_write(tmp_path, payload), spec)

    def test_zero_sample_count_rejected(self, tmp_path: Path, spec: ContractSpec) -> None:
        payload = dict(_VALID, sample_count=0)
        with pytest.raises(MetricParseError, match="sample_count"):
            parse_result_file(_write(tmp_path, payload), spec)
