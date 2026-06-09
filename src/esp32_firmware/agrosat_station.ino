
/**
 * AgroSat Intelligence — Firmware ESP32
 * ======================================
 * Estação Meteorológica Inteligente Inspirada em Satélites
 * Global Solution 2026.1 — FIAP
 *
 * Hardware:
 *   - ESP32 DevKit v1
 *   - Sensor DHT22   (Temperatura + Umidade)        → GPIO 4
 *   - Sensor BMP280  (Pressão + Altitude)            → I2C (SDA=21, SCL=22)
 *   - Sensor UV ML8511                               → GPIO 34 (ADC)
 *   - Pluviômetro (reed switch)                      → GPIO 5
 *   - Anemômetro (pulso)                             → GPIO 18
 *   - Display OLED SSD1306 128x64                    → I2C (SDA=21, SCL=22)
 *   - LED Status RGB                                 → GPIO 25, 26, 27
 *
 * Fluxo de dados:
 *   ESP32 → WiFi → AWS IoT Core (MQTT) → Lambda → DynamoDB → API REST → ML Pipeline
 *
 * Inspiração espacial:
 *   Mesma lógica de coleta multiespectral dos satélites Sentinel/Landsat,
 *   adaptada para ground truth de baixo custo no campo.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>       // MQTT
#include <ArduinoJson.h>        // JSON payload
#include <DHT.h>                // DHT22
#include <Adafruit_BMP280.h>    // BMP280
#include <Adafruit_SSD1306.h>   // Display OLED
#include <Wire.h>

// ─── Configurações ───────────────────────────────────────────────────────────
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";

// AWS IoT Core — substituir pelos seus endpoints
const char* MQTT_BROKER   = "xxxxxxxx.iot.sa-east-1.amazonaws.com";
const int   MQTT_PORT     = 8883;
const char* MQTT_TOPIC    = "agrosat/station/001/telemetry";
const char* DEVICE_ID     = "ESP32_STATION_001";

// Intervalo de leitura e publicação
const unsigned long READ_INTERVAL_MS  = 5000;   // 5s para leitura
const unsigned long SEND_INTERVAL_MS  = 60000;  // 60s para envio MQTT

// ─── Pinos ───────────────────────────────────────────────────────────────────
#define DHT_PIN         4
#define DHT_TYPE        DHT22
#define UV_SENSOR_PIN   34
#define RAIN_PIN        5
#define WIND_PIN        18
#define LED_RED_PIN     25
#define LED_GREEN_PIN   26
#define LED_BLUE_PIN    27

// ─── Display OLED ────────────────────────────────────────────────────────────
#define SCREEN_WIDTH    128
#define SCREEN_HEIGHT   64
#define OLED_RESET      -1
#define OLED_ADDR       0x3C

// ─── Objetos de Hardware ─────────────────────────────────────────────────────
DHT               dht(DHT_PIN, DHT_TYPE);
Adafruit_BMP280   bmp;
Adafruit_SSD1306  display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
WiFiClient        wifiClient;
PubSubClient      mqttClient(wifiClient);

// ─── Variáveis de Estado ─────────────────────────────────────────────────────
volatile unsigned long rainPulseCount = 0;   // Pulsos do pluviômetro
volatile unsigned long windPulseCount = 0;   // Pulsos do anemômetro

unsigned long lastReadTime    = 0;
unsigned long lastSendTime    = 0;
float         accumulatedRain = 0.0;         // mm acumulados no dia

// Estrutura de leitura
struct SensorReading {
    float temperature;      // °C (DHT22)
    float humidity;         // % (DHT22)
    float pressure;         // hPa (BMP280)
    float altitude;         // m (BMP280, pressão nível do mar=1013.25)
    float uvIndex;          // 0-11
    float rainfall_mm;      // mm
    float wind_speed_kmh;   // km/h
    unsigned long timestamp;
    bool  valid;
};

// ─── ISR Contadores ──────────────────────────────────────────────────────────
void IRAM_ATTR onRainPulse() {
    rainPulseCount++;    // Cada pulso = 0.2794 mm (Reed switch pluviômetro padrão)
}

void IRAM_ATTR onWindPulse() {
    windPulseCount++;
}

// ─── Conversão UV (ML8511) ───────────────────────────────────────────────────
float readUVIndex() {
    int   rawADC  = analogRead(UV_SENSOR_PIN);
    float voltage = (rawADC / 4095.0f) * 3.3f;
    // Fórmula de linearização ML8511
    float uvIntensity = mapFloat(voltage, 0.99f, 2.8f, 0.0f, 15.0f);
    return constrain(uvIntensity, 0.0f, 15.0f);
}

float mapFloat(float x, float in_min, float in_max, float out_min, float out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

// ─── Leitura de Sensores ─────────────────────────────────────────────────────
SensorReading readAllSensors() {
    SensorReading reading;
    reading.timestamp = millis();
    reading.valid     = true;
    
    // DHT22 — Temperatura e Umidade
    reading.temperature = dht.readTemperature();
    reading.humidity    = dht.readHumidity();
    if (isnan(reading.temperature) || isnan(reading.humidity)) {
        Serial.println("[WARN] DHT22: leitura inválida");
        reading.valid = false;
    }
    
    // BMP280 — Pressão e Altitude
    reading.pressure = bmp.readPressure() / 100.0F;  // Pa → hPa
    reading.altitude = bmp.readAltitude(1013.25);
    
    // UV
    reading.uvIndex = readUVIndex();
    
    // Pluviômetro (acumula por período)
    noInterrupts();
    unsigned long pulses = rainPulseCount;
    rainPulseCount = 0;
    interrupts();
    reading.rainfall_mm = pulses * 0.2794;
    accumulatedRain += reading.rainfall_mm;
    
    // Anemômetro (velocidade do vento)
    noInterrupts();
    unsigned long windPulses = windPulseCount;
    windPulseCount = 0;
    interrupts();
    // 1 rotação = 2 pulsos, circunferência = 1.5m → velocidade
    float rotations = windPulses / 2.0;
    reading.wind_speed_kmh = (rotations * 1.5 * 3.6) /
                             (READ_INTERVAL_MS / 1000.0);
    
    return reading;
}

// ─── Montar JSON Payload ──────────────────────────────────────────────────────
String buildPayload(const SensorReading& r) {
    StaticJsonDocument<512> doc;
    doc["device_id"]       = DEVICE_ID;
    doc["timestamp_unix"]  = (unsigned long)(millis() / 1000);
    doc["temperature_c"]   = round(r.temperature * 10) / 10.0;
    doc["humidity_pct"]    = round(r.humidity * 10) / 10.0;
    doc["pressure_hpa"]    = round(r.pressure * 10) / 10.0;
    doc["altitude_m"]      = round(r.altitude * 10) / 10.0;
    doc["uv_index"]        = round(r.uvIndex * 10) / 10.0;
    doc["rain_mm"]         = round(r.rainfall_mm * 100) / 100.0;
    doc["rain_acc_mm"]     = round(accumulatedRain * 100) / 100.0;
    doc["wind_kmh"]        = round(r.wind_speed_kmh * 10) / 10.0;
    doc["data_quality"]    = r.valid ? "GOOD" : "DEGRADED";
    doc["firmware_ver"]    = "1.2.0";
    
    String output;
    serializeJson(doc, output);
    return output;
}

// ─── Display OLED ────────────────────────────────────────────────────────────
void updateDisplay(const SensorReading& r) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    
    // Cabeçalho
    display.setCursor(0, 0);
    display.print("** AgroSat EST-001 **");
    display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
    
    // Dados em grid
    display.setCursor(0, 14);
    display.printf("Temp: %.1fC  Hum: %.0f%%\n", r.temperature, r.humidity);
    display.printf("Press: %.0f hPa\n", r.pressure);
    display.printf("UV: %.1f  Vento: %.0fkm/h\n", r.uvIndex, r.wind_speed_kmh);
    display.printf("Chuva: %.1fmm (acc%.0f)\n", r.rainfall_mm, accumulatedRain);
    
    // Status MQTT
    display.setCursor(0, 56);
    display.print(mqttClient.connected() ? "[WiFi OK] " : "[WiFi ERR]");
    display.print(millis() / 1000);
    display.print("s");
    
    display.display();
}

// ─── LED Status ──────────────────────────────────────────────────────────────
void setStatusLED(uint8_t r, uint8_t g, uint8_t b) {
    analogWrite(LED_RED_PIN,   r);
    analogWrite(LED_GREEN_PIN, g);
    analogWrite(LED_BLUE_PIN,  b);
}

// ─── Conexão WiFi e MQTT ─────────────────────────────────────────────────────
void connectWiFi() {
    Serial.print("[WiFi] Conectando a ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    setStatusLED(255, 100, 0);  // Laranja = conectando
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Conectado! IP: %s\n", WiFi.localIP().toString().c_str());
        setStatusLED(0, 255, 0);  // Verde = conectado
    } else {
        Serial.println("\n[WiFi] FALHA na conexão — modo offline");
        setStatusLED(255, 0, 0);  // Vermelho = erro
    }
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("[MQTT] Conectando ao broker...");
        if (mqttClient.connect(DEVICE_ID)) {
            Serial.println(" OK");
            mqttClient.subscribe("agrosat/station/001/cmd");  // Recebe comandos
        } else {
            Serial.printf(" Falhou (rc=%d). Tentando em 5s...\n", mqttClient.state());
            delay(5000);
        }
    }
}

// ─── Callback MQTT (comandos recebidos do servidor) ──────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    String message;
    for (unsigned int i = 0; i < length; i++) message += (char)payload[i];
    
    Serial.printf("[MQTT] Comando recebido: %s\n", message.c_str());
    
    // Comandos suportados: RESET_RAIN, CALIBRATE, STATUS
    if (message == "RESET_RAIN")  accumulatedRain = 0.0;
    if (message == "STATUS")      Serial.printf("[STATUS] Uptime=%lus\n", millis()/1000);
}

// ─── Setup ───────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("\n=== AgroSat ESP32 Station Firmware v1.2.0 ===");
    
    // LEDs
    pinMode(LED_RED_PIN, OUTPUT);
    pinMode(LED_GREEN_PIN, OUTPUT);
    pinMode(LED_BLUE_PIN, OUTPUT);
    setStatusLED(0, 0, 255);  // Azul = iniciando
    
    // I2C
    Wire.begin(21, 22);
    
    // OLED
    if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
        Serial.println("[ERR] Display OLED não encontrado");
    }
    display.clearDisplay();
    display.setTextSize(2);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(10, 20);
    display.println("AgroSat");
    display.setTextSize(1);
    display.setCursor(20, 45);
    display.println("Iniciando...");
    display.display();
    
    // DHT22
    dht.begin();
    
    // BMP280
    if (!bmp.begin(0x76)) {
        Serial.println("[ERR] BMP280 não encontrado");
    } else {
        bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                        Adafruit_BMP280::SAMPLING_X2,
                        Adafruit_BMP280::SAMPLING_X16,
                        Adafruit_BMP280::FILTER_X16,
                        Adafruit_BMP280::STANDBY_MS_500);
    }
    
    // ISR dos pulsos
    attachInterrupt(digitalPinToInterrupt(RAIN_PIN), onRainPulse, FALLING);
    attachInterrupt(digitalPinToInterrupt(WIND_PIN), onWindPulse, RISING);
    
    // WiFi e MQTT
    connectWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
    
    Serial.println("[OK] Setup completo — iniciando coleta de dados");
    setStatusLED(0, 255, 0);
}

// ─── Loop Principal ───────────────────────────────────────────────────────────
void loop() {
    unsigned long now = millis();
    
    // Manter MQTT conectado
    if (!mqttClient.connected()) reconnectMQTT();
    mqttClient.loop();
    
    // Leitura periódica dos sensores
    if (now - lastReadTime >= READ_INTERVAL_MS) {
        lastReadTime = now;
        
        SensorReading reading = readAllSensors();
        
        // Atualizar display
        updateDisplay(reading);
        
        // Log serial
        Serial.printf("[READ] T=%.1fC H=%.0f%% P=%.0fhPa UV=%.1f W=%.0fkm/h R=%.1fmm\n",
            reading.temperature, reading.humidity, reading.pressure,
            reading.uvIndex, reading.wind_speed_kmh, reading.rainfall_mm);
        
        // Envio MQTT periódico
        if (now - lastSendTime >= SEND_INTERVAL_MS) {
            lastSendTime = now;
            
            String payload = buildPayload(reading);
            bool ok = mqttClient.publish(MQTT_TOPIC, payload.c_str(), true);
            
            if (ok) {
                Serial.println("[MQTT] Payload enviado com sucesso");
                setStatusLED(0, 200, 200);  // Ciano = enviando
                delay(200);
                setStatusLED(0, 255, 0);    // Verde = ok
            } else {
                Serial.println("[MQTT] Falha no envio");
                setStatusLED(255, 0, 0);
            }
        }
    }
}
