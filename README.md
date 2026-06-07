# FIAP - Faculdade de Informática e Administração Paulista

<img width="2385" height="642" alt="image" src="https://github.com/user-attachments/assets/594c28cc-66ae-40ac-b8a6-8c39e6f14de4" />

# 🛰️ AgroSat Intelligence
## Previsão de Safra com NDVI Satelital e Estação Meteorológica ESP32

> **Global Solution 2026.1 — FIAP**  
> Tema: Economia Espacial — *"Como a IA pode transformar a nova economia espacial e gerar impacto positivo na Terra?"*

## 👨‍🎓 Integrantes
- [CAUAN OTTO RODRIGUES SOUSA (RM567940)](https://www.linkedin.com/in/cauanotto)
- [FERNANDO A GURGEL (RM567606)](https://www.linkedin.com/in/fernando-gurgel-75aa8369)
- [IRACI MONTEIRO SOUZA (RM567544)](https://www.linkedin.com/in/iraci-souza-bab42034)
- [MARIA LUISA RODRIGUES NASCIMENTO (RM567659)](https://www.linkedin.com/in/malu-rodrigues-bb756b271)
- [RAFAELA TORRES MARTINS (RM567735)](https://www.linkedin.com/in/rafaela-torres222)

## 👩‍🏫 Professores
- **Tutor(a):** [ANA CRISTINA DOS SANTOS](https://www.linkedin.com/company/inova-fusca)
- **Coordenador(a):** [ANDRÉ GODOI](https://www.linkedin.com/in/andregodoichiovato)

---

## 🚀 Proposta da Solução

O **AgroSat Intelligence** é um sistema completo de **previsão de produtividade agrícola** que combina:

1. **Dados NDVI de satélite** (Sentinel-2 / Landsat) para monitoramento da vegetação
2. **Estação meteorológica IoT baseada em ESP32** para dados de campo em tempo real
3. **Pipeline de Machine Learning** (Random Forest + Gradient Boosting) para previsão de safra
4. **Infraestrutura serverless na AWS** para processamento e armazenamento escalável
5. **Dashboard web interativo** para visualização e tomada de decisão

A solução responde diretamente ao desafio da GS 2026.1, conectando tecnologias espaciais (imagens de satélite, NDVI multiespectral) com IA para **gerar impacto positivo no agronegócio brasileiro**.

---

## 🏗️ Arquitetura da Solução

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE COLETA                             │
│                                                                     │
│  🛰️ Satélite         📡 ESP32 Station        🌐 APIs Externas       │
│  Sentinel-2 NDVI  →  DHT22, BMP280,     →  INMET, OpenWeather      │
│  Landsat-8        →  UV, Rain, Wind      →  NASA EarthData          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ MQTT / HTTPS
┌──────────────────────────▼──────────────────────────────────────────┐
│                     AWS IoT CORE + LAMBDA                           │
│                                                                     │
│  IoT Rule → Lambda (ingest) → DynamoDB → S3 (raw data lake)         │
│                            → SNS (alertas)                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                    PIPELINE DE ML (Python)                          │
│                                                                     │
│  Feature Engineering → Random Forest → Gradient Boosting            │
│  NDVI + Clima + GDA → Ensemble Model → Previsão (sacas/ha)          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ API REST
┌──────────────────────────▼──────────────────────────────────────────┐
│                    DASHBOARD WEB (HTML/JS)                          │
│                                                                     │
│  Mapa NDVI  │  Gráficos Temporais  │  KPIs  │  Previsão de Safra    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura do Repositório

```
agrosat-intelligence/
│
├── README.md                          # Este arquivo
├── requirements.txt                   # Dependências Python
│
├── src/
│   ├── ndvi_pipeline.py               # Pipeline principal de ML
│   ├── esp32_firmware/
│   │   └── agrosat_station.ino        # Firmware ESP32 (Arduino C++)
│   └── aws/
│       └── lambda_ingest.py           # Função Lambda de ingestão
│
├── dashboard/
│   └── index.html                     # Dashboard web interativo
│
├── docs/
│   ├── arquitetura.png                # Diagrama de arquitetura
│   └── AgroSat_GS2026.pdf            # Documentação completa
│
└── output/                            # Resultados do pipeline (gerado)
    ├── ndvi_data.csv
    ├── weather_data.csv
    ├── features.csv
    └── results.json
```

---

## ⚙️ Tecnologias Utilizadas

### Machine Learning & Data
| Tecnologia | Uso |
|---|---|
| Python 3.12 | Linguagem principal do pipeline |
| scikit-learn | Random Forest, Gradient Boosting, métricas |
| pandas / numpy | Manipulação e análise de dados |
| NDVI (Sentinel-2) | Índice de vegetação por diferença normalizada |
| VCI (Vegetation Condition Index) | Índice de condição da vegetação |

### IoT / Hardware
| Componente | Função |
|---|---|
| ESP32 DevKit v1 | Microcontrolador principal |
| DHT22 | Temperatura (±0.5°C) e Umidade (±2%) |
| BMP280 | Pressão atmosférica e altitude |
| Sensor UV ML8511 | Índice UV (0-15) |
| Pluviômetro (reed switch) | Precipitação acumulada (0.2794 mm/pulso) |
| Anemômetro | Velocidade do vento (km/h) |
| Display OLED SSD1306 | Visualização local 128×64 px |

### Cloud AWS
| Serviço | Uso |
|---|---|
| AWS IoT Core | Broker MQTT para dados ESP32 |
| AWS Lambda | Processamento serverless (ingestão) |
| Amazon DynamoDB | Armazenamento NoSQL de telemetria |
| Amazon S3 | Data lake para dados brutos |
| Amazon SNS | Notificações e alertas automáticos |

---

## 🔬 Sobre o NDVI

O **NDVI** (Normalized Difference Vegetation Index) é calculado a partir de bandas espectrais de satélites:

```
NDVI = (NIR - RED) / (NIR + RED)
```

| Faixa NDVI | Interpretação |
|---|---|
| < 0.2 | Solo exposto / vegetação morta |
| 0.2 – 0.4 | Vegetação esparsa |
| 0.4 – 0.6 | Vegetação moderada |
| 0.6 – 0.8 | Vegetação densa e saudável |
| > 0.8 | Vegetação muito densa |

---

## 🧠 Modelo de Machine Learning

O ensemble combina dois modelos:

**Random Forest**
- 200 árvores de decisão
- Profundidade máxima: 8
- Agrega previsões por votação (menor variância)

**Gradient Boosting**
- 150 estimadores
- Taxa de aprendizado: 0.05
- Redução sequencial de resíduos

**Features utilizadas:**
- NDVI médias móveis (7, 14, 30 dias)
- VCI (Vegetation Condition Index)
- Precipitação acumulada (7 e 30 dias)
- Temperatura média móvel
- Graus-dia acumulados (GDA)
- Índice térmico × NDVI
- Índice UV

---

## 🚀 Como Executar

### Pré-requisitos
```bash
pip install -r requirements.txt
```

### Rodar pipeline completo
```bash
python src/ndvi_pipeline.py
```

### Saída esperada
```
============================================================
  AgroSat Intelligence — Pipeline de Previsão de Safra
============================================================

[1/4] Ingerindo dados NDVI do satélite...
      ✓ 180 observações NDVI geradas

[2/4] Coletando dados da estação meteorológica ESP32...
      ✓ 180 registros meteorológicos coletados

[3/4] Construindo matriz de features...
      ✓ 136 amostras, 22 variáveis

[4/4] Treinando modelos de Machine Learning...

============================================================
  RESULTADOS DA PREVISÃO
============================================================
  Previsão de Produtividade : 58.3 sc/ha
  Classificação             : BOM (55-65 sc/ha)

  Desempenho dos Modelos:
    random_forest        R²=0.941  MAE=1.8 sc/ha
    gradient_boosting    R²=0.938  MAE=1.9 sc/ha
    ensemble             R²=0.952  MAE=1.6 sc/ha
============================================================
```

---

## 📊 Resultados Esperados

- **Acurácia (R²):** ≥ 0.93 no ensemble
- **Erro absoluto médio (MAE):** < 2 sc/ha
- **Latência de ingestão IoT:** < 2s (ESP32 → DynamoDB)
- **Período de previsão:** 30, 60 e 90 dias antes da colheita
- **Culturas suportadas:** Soja, Milho, Cana-de-açúcar

---

## 🌍 Impacto e Aplicabilidade

- Redução de desperdício de insumos (fertilizantes, defensivos) em até **30%**
- Antecipação de quebras de safra com **60-90 dias de antecedência**
- Custo da estação ESP32: **~R$ 280** (vs R$ 15.000+ de estações comerciais)
- Escalável para monitoramento de **milhares de talhões** via cloud

---

## 📄 Documentação Completa

Ver arquivo `docs/AgroSat_GS2026.pdf` e apresentação `docs/AgroSat_Apresentacao.pptx`.

---

*Desenvolvido para a Global Solution 2026.1 — FIAP — Inteligência Artificial*
