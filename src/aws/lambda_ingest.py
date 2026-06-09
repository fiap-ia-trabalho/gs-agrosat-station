
"""
AgroSat Intelligence — AWS Lambda Function
===========================================
Função serverless que recebe dados da estação ESP32 via AWS IoT Core (MQTT)
e os persiste no DynamoDB, disparando o pipeline de ML quando acúmulo
de dados é suficiente.

Trigger: IoT Core Rule → Lambda
Output: DynamoDB + SNS notification + S3 (dados brutos)

Deploy:
    aws lambda create-function \\
        --function-name agrosat-ingest \\
        --runtime python3.12 \\
        --handler lambda_ingest.handler \\
        --role arn:aws:iam::ACCOUNT:role/agrosat-lambda-role \\
        --zip-file fileb://lambda_ingest.zip
"""

import json
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal

# ─── Clientes AWS ─────────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name="sa-east-1")
s3_client = boto3.client("s3", region_name="sa-east-1")
sns_client = boto3.client("sns", region_name="sa-east-1")

# ─── Configuração (variáveis de ambiente no Lambda) ──────────────────────────
TABLE_NAME   = os.environ.get("DYNAMODB_TABLE", "agrosat-telemetry")
BUCKET_NAME  = os.environ.get("S3_BUCKET", "agrosat-raw-data")
SNS_TOPIC    = os.environ.get("SNS_TOPIC_ARN", "arn:aws:sns:sa-east-1:ACCOUNT:agrosat-alerts")

# Limiares para alertas automáticos
ALERT_THRESHOLDS = {
    "temperature_c":  {"max": 38.0, "min": 5.0,  "label": "Temperatura Crítica"},
    "humidity_pct":   {"max": 95.0, "min": 20.0, "label": "Umidade Crítica"},
    "uv_index":       {"max": 9.0,               "label": "UV Extremo"},
    "wind_kmh":       {"max": 60.0,              "label": "Vento Forte"},
}


def handler(event, context):
    """
    Ponto de entrada da Lambda.
    Evento esperado: payload JSON do ESP32 via MQTT rule.
    """
    print(f"[LAMBDA] Evento recebido: {json.dumps(event)}")
    
    table = dynamodb.Table(TABLE_NAME)
    
    # O IoT Core pode enviar múltiplos registros em batch
    records = event if isinstance(event, list) else [event]
    
    processed = 0
    alerts_sent = 0
    
    for record in records:
        try:
            # ── Enriquecer dados ──────────────────────────────────────────────
            enriched = _enrich_record(record)
            
            # ── Persistir no DynamoDB ─────────────────────────────────────────
            # Partition key: device_id | Sort key: timestamp_iso
            table.put_item(Item=enriched)
            
            # ── Backup bruto no S3 ────────────────────────────────────────────
            _save_to_s3(enriched)
            
            # ── Verificar limiares e enviar alertas ───────────────────────────
            alerts = _check_thresholds(enriched)
            for alert_msg in alerts:
                sns_client.publish(
                    TopicArn=SNS_TOPIC,
                    Message=alert_msg,
                    Subject="AgroSat — Alerta Meteorológico",
                )
                alerts_sent += 1
            
            processed += 1
            
        except Exception as exc:
            print(f"[ERROR] Falha ao processar registro: {exc}")
            # Não relança — evita retry em loop para dados malformados
    
    response = {
        "statusCode": 200,
        "body": {
            "processed": processed,
            "alerts_sent": alerts_sent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    
    print(f"[LAMBDA] Concluído: {json.dumps(response['body'])}")
    return response


def _enrich_record(record: dict) -> dict:
    """Adiciona metadados e converte tipos para DynamoDB."""
    now = datetime.now(timezone.utc)
    
    enriched = {}
    for k, v in record.items():
        # DynamoDB não aceita float nativo — usar Decimal
        if isinstance(v, float):
            enriched[k] = Decimal(str(round(v, 4)))
        else:
            enriched[k] = v
    
    # Chaves compostas para acesso eficiente
    enriched["pk"]            = f"STATION#{record.get('device_id', 'UNKNOWN')}"
    enriched["sk"]            = f"TS#{now.strftime('%Y%m%dT%H%M%S')}Z"
    enriched["timestamp_iso"] = now.isoformat()
    enriched["year_month"]    = now.strftime("%Y-%m")     # GSI para queries mensais
    enriched["ingested_at"]   = now.isoformat()
    enriched["ttl"]           = int(now.timestamp()) + 90 * 24 * 3600  # TTL: 90 dias
    
    # Calcular índice de conforto térmico (Heat Index simplificado)
    temp = float(enriched.get("temperature_c", 25))
    hum  = float(enriched.get("humidity_pct", 60))
    hi   = _heat_index(temp, hum)
    enriched["heat_index"] = Decimal(str(hi))
    
    return enriched


def _heat_index(temp_c: float, humidity: float) -> float:
    """Índice de calor (Rothfusz, adaptado para Celsius)."""
    t = temp_c * 9 / 5 + 32  # → Fahrenheit
    h = humidity
    if t < 80:
        return round((temp_c + (t + 61 + (t - 68) * 1.2 + h * 0.094) / 2 - 32) * 5 / 9, 1)
    hi_f = (-42.379 + 2.04901523*t + 10.14333127*h
            - 0.22475541*t*h - 6.83783e-3*t**2
            - 5.481717e-2*h**2 + 1.22874e-3*t**2*h
            + 8.5282e-4*t*h**2 - 1.99e-6*t**2*h**2)
    return round((hi_f - 32) * 5 / 9, 1)


def _save_to_s3(record: dict):
    """Salva dado bruto no S3 com particionamento por data."""
    now = datetime.now(timezone.utc)
    key = (f"raw/{record.get('pk', 'UNKNOWN')}/"
           f"year={now.year}/month={now.month:02d}/day={now.day:02d}/"
           f"{now.strftime('%H%M%S')}.json")
    
    # Converte Decimal de volta para float para serialização JSON
    serializable = {k: float(v) if isinstance(v, Decimal) else v
                    for k, v in record.items()}
    
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(serializable, ensure_ascii=False),
        ContentType="application/json",
    )


def _check_thresholds(record: dict) -> list[str]:
    """Verifica limiares e retorna lista de mensagens de alerta."""
    alerts = []
    device = record.get("device_id", "ESTAÇÃO")
    
    for field, limits in ALERT_THRESHOLDS.items():
        value = float(record.get(field, 0))
        label = limits["label"]
        
        if "max" in limits and value > limits["max"]:
            alerts.append(
                f"⚠️ ALERTA {label}\n"
                f"Dispositivo: {device}\n"
                f"Valor atual: {value} (máximo: {limits['max']})\n"
                f"Hora: {record.get('timestamp_iso', 'N/A')}"
            )
        if "min" in limits and value < limits["min"]:
            alerts.append(
                f"⚠️ ALERTA {label}\n"
                f"Dispositivo: {device}\n"
                f"Valor atual: {value} (mínimo: {limits['min']})\n"
                f"Hora: {record.get('timestamp_iso', 'N/A')}"
            )
    
    return alerts
