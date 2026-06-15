from __future__ import annotations

import json
import math
import re
import unicodedata
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier, XGBRegressor


def normalize_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.casefold())
    return re.sub(r"_+", "_", text).strip("_")


def normalize_product(value: Any) -> str:
    normalized = normalize_key(value)
    return {
        "tomate": "tomate_rojo",
        "tomate_rojo_202": "tomate_rojo",
        "chile_jalapeno": "chile_verde",
    }.get(normalized, normalized)


def decena_to_date(year: Any, month: Any, day_block: Any) -> pd.Timestamp:
    year_int = int(year)
    month_int = int(month)
    block_int = int(day_block)
    day = {1: 10, 2: 20, 3: monthrange(year_int, month_int)[1]}[block_int]
    return pd.Timestamp(date(year_int, month_int, day))


def read_sheet_aliases(
    path: Path,
    aliases: Iterable[str],
    *,
    fallback_first: bool = False,
) -> pd.DataFrame:
    with pd.ExcelFile(path) as excel:
        available = {normalize_key(name): name for name in excel.sheet_names}
        for alias in aliases:
            resolved = available.get(normalize_key(alias))
            if resolved:
                return pd.read_excel(path, sheet_name=resolved)
        if fallback_first and excel.sheet_names:
            return pd.read_excel(path, sheet_name=excel.sheet_names[0])
    return pd.DataFrame()


def write_parquet_with_metadata(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    metadata: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)
    output_path.with_suffix(output_path.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def build_preprocessor(
    frame: pd.DataFrame,
    feature_columns: list[str],
) -> ColumnTransformer:
    feature_columns = [column for column in feature_columns if frame[column].notna().any()]
    categorical = [
        column
        for column in feature_columns
        if not pd.api.types.is_numeric_dtype(frame[column])
        and not pd.api.types.is_datetime64_any_dtype(frame[column])
    ]
    numeric = [column for column in feature_columns if column not in categorical]
    return ColumnTransformer(
        [
            (
                "numericas",
                Pipeline([("imputar", SimpleImputer(strategy="median"))]),
                numeric,
            ),
            (
                "categoricas",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="most_frequent")),
                        ("codificar", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )


def make_regression_pipeline(
    frame: pd.DataFrame,
    feature_columns: list[str],
    *,
    objective: str = "reg:squarederror",
    quantile_alpha: float | None = None,
    random_state: int = 42,
) -> Pipeline:
    params: dict[str, Any] = {
        "objective": objective,
        "n_estimators": 180,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_lambda": 1.0,
        "random_state": random_state,
        "n_jobs": 1,
    }
    if quantile_alpha is not None:
        params["quantile_alpha"] = quantile_alpha
    return Pipeline(
        [
            ("preprocesar", build_preprocessor(frame, feature_columns)),
            ("modelo", XGBRegressor(**params)),
        ]
    )


def make_classifier_pipeline(
    frame: pd.DataFrame,
    feature_columns: list[str],
    *,
    random_state: int = 42,
) -> Pipeline:
    return Pipeline(
        [
            ("preprocesar", build_preprocessor(frame, feature_columns)),
            (
                "modelo",
                XGBClassifier(
                    objective="binary:logistic",
                    eval_metric="logloss",
                    n_estimators=160,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    random_state=random_state,
                    n_jobs=1,
                ),
            ),
        ]
    )


def temporal_train_test(
    frame: pd.DataFrame,
    date_column: str,
    *,
    test_fraction: float = 0.2,
) -> tuple[pd.Index, pd.Index, pd.Timestamp]:
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    unique_dates = pd.Series(dates.dropna().unique()).sort_values().reset_index(drop=True)
    if len(unique_dates) < 5:
        raise ValueError("Se requieren al menos cinco fechas para validacion temporal.")
    split_position = min(
        len(unique_dates) - 1,
        max(1, int(math.floor(len(unique_dates) * (1 - test_fraction)))),
    )
    cutoff = pd.Timestamp(unique_dates.iloc[split_position])
    train_index = frame.index[dates < cutoff]
    test_index = frame.index[dates >= cutoff]
    if train_index.empty or test_index.empty:
        raise ValueError("La division temporal produjo un conjunto vacio.")
    return train_index, test_index, cutoff


def regression_metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    valid = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if valid.empty:
        return {"mae": math.nan, "rmse": math.nan, "mape": math.nan}
    denominator = valid["actual"].abs().replace(0, np.nan)
    return {
        "mae": float(mean_absolute_error(valid["actual"], valid["predicted"])),
        "rmse": float(mean_squared_error(valid["actual"], valid["predicted"]) ** 0.5),
        "mape": float(
            ((valid["actual"] - valid["predicted"]).abs() / denominator).dropna().mean()
        ),
    }


def probability_below_from_interval(
    threshold: float,
    median: float,
    lower: float,
    upper: float,
) -> float:
    sigma = max((upper - lower) / 2.563, 1e-6)
    z_score = (threshold - median) / sigma
    return float(0.5 * (1 + math.erf(z_score / math.sqrt(2))))


def probability_shortfall_from_interval(
    reference: float,
    shortfall: float,
    median: float,
    lower: float,
    upper: float,
) -> float:
    return probability_below_from_interval(reference * (1 - shortfall), median, lower, upper)


def model_feature_importance(pipeline: Pipeline) -> pd.DataFrame:
    preprocessor = pipeline.named_steps["preprocesar"]
    model = pipeline.named_steps["modelo"]
    names = preprocessor.get_feature_names_out()
    values = getattr(model, "feature_importances_", np.zeros(len(names)))
    return (
        pd.DataFrame({"variable": names, "importancia": values})
        .sort_values("importancia", ascending=False)
        .reset_index(drop=True)
    )
