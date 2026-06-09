
"""
AgroSat Intelligence - Pipeline de Previsão de Safra com NDVI Satelital
=======================================================================
Global Solution 2026.1 - FIAP - Inteligência Artificial
Tema: Economia Espacial

Pipeline principal de ingestão, processamento e predição de safra
utilizando dados NDVI de satélite e dados meteorológicos (simulando
estação ESP32 inspirada em satélites).

Autores: [Nome do Grupo]
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# 1. SIMULAÇÃO DE DADOS NDVI (representando ingestão via API de satélite)
# ─────────────────────────────────────────────────────────────────────────────

def generate_ndvi_time_series(
    latitude: float = -22.5,
    longitude: float = -47.0,
    culture: str = "soja",
    days: int = 180,
    start_date: str = "2025-09-01"
) -> pd.DataFrame:
    """
    Simula série temporal de NDVI como seria recebida via API Sentinel-2 / Landsat.
    Em produção: substituir por requisição à API do Copernicus ou NASA EarthData.

    Parâmetros:
        latitude  : Latitude da fazenda (ex: -22.5 para SP)
        longitude : Longitude da fazenda
        culture   : Cultura plantada ('soja', 'milho', 'cana')
        days      : Período de monitoramento em dias
        start_date: Data de início do plantio
    
    Retorna:
        DataFrame com colunas: date, ndvi, cloud_cover, pixel_quality
    """
    np.random.seed(42)
    dates = pd.date_range(start=start_date, periods=days, freq="D")
    
    # Curva NDVI fenológica realista: crescimento → pico → senescência
    t = np.linspace(0, np.pi, days)
    base_ndvi = 0.2 + 0.65 * np.sin(t) ** 1.5
    
    # Ruído realista (nuvens, variação climática)
    noise = np.random.normal(0, 0.03, days)
    cloud_events = np.random.choice([0, 1], size=days, p=[0.75, 0.25])
    
    ndvi = np.clip(base_ndvi + noise - cloud_events * 0.15, 0.05, 0.95)
    cloud_cover = np.random.uniform(0, 100, days) * cloud_events
    pixel_quality = np.where(cloud_cover > 60, "LOW", np.where(cloud_cover > 20, "MEDIUM", "HIGH"))
    
    return pd.DataFrame({
        "date": dates,
        "latitude": latitude,
        "longitude": longitude,
        "culture": culture,
        "ndvi": ndvi.round(4),
        "cloud_cover_pct": cloud_cover.round(1),
        "pixel_quality": pixel_quality
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. SIMULAÇÃO DA ESTAÇÃO METEOROLÓGICA ESP32
# ─────────────────────────────────────────────────────────────────────────────

def generate_weather_station_data(
    days: int = 180,
    start_date: str = "2025-09-01"
) -> pd.DataFrame:
    """
    Simula dados de estação meteorológica baseada em ESP32 com sensores:
    - DHT22: temperatura e umidade
    - BMP280: pressão atmosférica
    - Anemômetro: velocidade do vento
    - Pluviômetro: precipitação
    - Sensor UV: índice UV (inspirado em sensores de satélite)

    Em produção: dados chegam via MQTT → AWS IoT Core → Lambda → DynamoDB.
    """
    np.random.seed(7)
    dates = pd.date_range(start=start_date, periods=days, freq="D")
    
    # Temperatura sazonal realista para SP (primavera → verão → outono)
    t = np.linspace(0, 2 * np.pi, days)
    temp_base = 24 + 6 * np.sin(t - np.pi / 3)
    temp = temp_base + np.random.normal(0, 1.5, days)
    
    # Precipitação (período chuvoso de nov a fev)
    rain_prob = 0.15 + 0.35 * np.sin(t - np.pi / 4).clip(0)
    rain = np.random.exponential(8, days) * np.random.binomial(1, rain_prob, days)
    
    humidity = np.clip(50 + 20 * np.sin(t) + np.random.normal(0, 5, days), 30, 98)
    pressure = np.clip(1013 + np.random.normal(0, 4, days), 990, 1030)
    wind_speed = np.abs(np.random.normal(8, 3, days))
    uv_index = np.clip(5 + 4 * np.sin(t) + np.random.normal(0, 0.8, days), 0, 11)
    
    # Graus-dia acumulados (GDA) — essencial para fenologia de culturas
    gda_daily = np.maximum(0, temp - 10)  # base 10°C
    gda_cumulative = np.cumsum(gda_daily)
    
    return pd.DataFrame({
        "date": dates,
        "temp_celsius": temp.round(1),
        "humidity_pct": humidity.round(1),
        "pressure_hpa": pressure.round(1),
        "rain_mm": rain.round(1),
        "wind_speed_kmh": wind_speed.round(1),
        "uv_index": uv_index.round(1),
        "gda_daily": gda_daily.round(1),
        "gda_cumulative": gda_cumulative.round(1),
        "source": "ESP32_STATION_001"
    })


# ─────────────────────────────────────────────────────────────────────────────
# 3. FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_matrix(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Constrói matriz de features para o modelo de ML combinando:
    - Features NDVI: médias móveis, acúmulo, variação
    - Features climáticas: totais por período fenológico
    - Features derivadas: estresse hídrico, índice de vigor (VCI)
    """
    df = pd.merge(ndvi_df, weather_df, on="date", how="inner")
    
    # Filtra apenas pixels de boa qualidade
    df_clean = df[df["pixel_quality"] != "LOW"].copy()
    
    # ── Features NDVI ──
    df_clean["ndvi_ma7"]  = df_clean["ndvi"].rolling(7, min_periods=1).mean()
    df_clean["ndvi_ma14"] = df_clean["ndvi"].rolling(14, min_periods=1).mean()
    df_clean["ndvi_ma30"] = df_clean["ndvi"].rolling(30, min_periods=1).mean()
    df_clean["ndvi_max"]  = df_clean["ndvi"].expanding().max()
    df_clean["ndvi_std"]  = df_clean["ndvi"].rolling(14, min_periods=2).std().fillna(0)
    
    # Vegetation Condition Index (VCI) — análogo ao usado em satélites
    ndvi_min_hist = 0.15
    ndvi_max_hist = 0.90
    df_clean["vci"] = ((df_clean["ndvi"] - ndvi_min_hist) /
                       (ndvi_max_hist - ndvi_min_hist) * 100).clip(0, 100)
    
    # ── Features Climáticas ──
    df_clean["rain_7d"]  = df_clean["rain_mm"].rolling(7, min_periods=1).sum()
    df_clean["rain_30d"] = df_clean["rain_mm"].rolling(30, min_periods=1).sum()
    df_clean["temp_ma7"] = df_clean["temp_celsius"].rolling(7, min_periods=1).mean()
    
    # Índice de Estresse Hídrico (Water Stress Index)
    df_clean["water_stress"] = (
        1 - (df_clean["rain_30d"] / df_clean["rain_30d"].max())
    ).clip(0, 1)
    
    # Temperatura acumulada × NDVI (proxy de produtividade)
    df_clean["thermal_ndvi_idx"] = df_clean["gda_cumulative"] * df_clean["ndvi_ma14"]
    
    return df_clean.dropna()


# ─────────────────────────────────────────────────────────────────────────────
# 4. MODELO DE MACHINE LEARNING — RANDOM FOREST + GRADIENT BOOSTING
# ─────────────────────────────────────────────────────────────────────────────

def train_yield_model(feature_df: pd.DataFrame) -> dict:
    """
    Treina modelo ensemble para previsão de produtividade (sacas/ha).
    Utiliza Random Forest + Gradient Boosting (ensemble stacking).
    
    Target sintético: correlacionado com VCI, GDA e precipitação
    (em produção: substituir por dados históricos de safra da CONAB/MAPA).
    """
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import r2_score, mean_absolute_error
    
    feature_cols = [
        "ndvi_ma14", "ndvi_ma30", "ndvi_max", "ndvi_std",
        "vci", "water_stress", "rain_30d", "temp_ma7",
        "gda_cumulative", "thermal_ndvi_idx", "uv_index"
    ]
    
    # Target sintético: produtividade soja (sacas/ha), base histórica ~55 sc/ha
    np.random.seed(99)
    yield_target = (
        35
        + 25 * feature_df["vci"] / 100
        + 0.002 * feature_df["gda_cumulative"]
        - 10 * feature_df["water_stress"]
        + np.random.normal(0, 2, len(feature_df))
    ).clip(20, 90)
    
    X = feature_df[feature_cols].fillna(0)
    y = yield_target
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Random Forest
    rf = Pipeline([
        ("scaler", StandardScaler()),
        ("model", RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1))
    ])
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)
    rf_r2  = r2_score(y_test, rf_pred)
    rf_mae = mean_absolute_error(y_test, rf_pred)
    
    # Gradient Boosting
    gb = Pipeline([
        ("scaler", StandardScaler()),
        ("model", GradientBoostingRegressor(n_estimators=150, learning_rate=0.05,
                                            max_depth=4, random_state=42))
    ])
    gb.fit(X_train, y_train)
    gb_pred = gb.predict(X_test)
    gb_r2  = r2_score(y_test, gb_pred)
    gb_mae = mean_absolute_error(y_test, gb_pred)
    
    # Ensemble prediction (média ponderada)
    ensemble_pred = 0.5 * rf_pred + 0.5 * gb_pred
    ens_r2  = r2_score(y_test, ensemble_pred)
    ens_mae = mean_absolute_error(y_test, ensemble_pred)
    
    # Feature importance (RF)
    importances = dict(zip(
        feature_cols,
        rf.named_steps["model"].feature_importances_.round(4)
    ))
    
    current_yield_prediction = float(
        (0.5 * rf.predict(X.tail(1)) + 0.5 * gb.predict(X.tail(1)))[0]
    )
    
    results = {
        "models": {
            "random_forest": {"r2": round(rf_r2, 4), "mae_sc_ha": round(rf_mae, 2)},
            "gradient_boosting": {"r2": round(gb_r2, 4), "mae_sc_ha": round(gb_mae, 2)},
            "ensemble": {"r2": round(ens_r2, 4), "mae_sc_ha": round(ens_mae, 2)}
        },
        "feature_importance": importances,
        "current_prediction_sc_ha": round(current_yield_prediction, 1),
        "prediction_class": _classify_yield(current_yield_prediction),
        "timestamp": datetime.now().isoformat()
    }
    
    return results


def _classify_yield(yield_sc_ha: float) -> str:
    if yield_sc_ha >= 65: return "EXCELENTE (≥65 sc/ha)"
    if yield_sc_ha >= 55: return "BOM (55-65 sc/ha)"
    if yield_sc_ha >= 45: return "MÉDIO (45-55 sc/ha)"
    return "BAIXO (<45 sc/ha)"


# ─────────────────────────────────────────────────────────────────────────────
# 5. PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    latitude: float = -22.5,
    longitude: float = -47.0,
    culture: str = "soja",
    output_dir: str = "./output"
) -> dict:
    """
    Executa o pipeline completo de previsão de safra.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("  AgroSat Intelligence — Pipeline de Previsão de Safra")
    print("=" * 60)
    
    print("\n[1/4] Ingerindo dados NDVI do satélite...")
    ndvi_df = generate_ndvi_time_series(latitude, longitude, culture)
    ndvi_df.to_csv(f"{output_dir}/ndvi_data.csv", index=False)
    print(f"      ✓ {len(ndvi_df)} observações NDVI geradas")
    
    print("\n[2/4] Coletando dados da estação meteorológica ESP32...")
    weather_df = generate_weather_station_data()
    weather_df.to_csv(f"{output_dir}/weather_data.csv", index=False)
    print(f"      ✓ {len(weather_df)} registros meteorológicos coletados")
    
    print("\n[3/4] Construindo matriz de features...")
    features_df = build_feature_matrix(ndvi_df, weather_df)
    features_df.to_csv(f"{output_dir}/features.csv", index=False)
    print(f"      ✓ {len(features_df)} amostras, {features_df.shape[1]} variáveis")
    
    print("\n[4/4] Treinando modelos de Machine Learning...")
    results = train_yield_model(features_df)
    
    with open(f"{output_dir}/results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("  RESULTADOS DA PREVISÃO")
    print("=" * 60)
    print(f"  Previsão de Produtividade : {results['current_prediction_sc_ha']} sc/ha")
    print(f"  Classificação             : {results['prediction_class']}")
    print(f"\n  Desempenho dos Modelos:")
    for model_name, metrics in results["models"].items():
        print(f"    {model_name:20s} R²={metrics['r2']:.3f}  MAE={metrics['mae_sc_ha']:.1f} sc/ha")
    print(f"\n  Top-3 Features Mais Importantes:")
    top3 = sorted(results["feature_importance"].items(), key=lambda x: x[1], reverse=True)[:3]
    for feat, imp in top3:
        print(f"    {feat:25s} {imp:.3f}")
    print("=" * 60)
    
    return results


if __name__ == "__main__":
    results = run_pipeline()
    print("\n✓ Pipeline concluído. Resultados em ./output/")
