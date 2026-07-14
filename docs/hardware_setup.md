# Axis - Hardware Quraşdırma

## Tələb olunan Komponentlər

| Komponent | Say | Qeyd |
|-----------|-----|------|
| ESP32 Development Board | 1 | ESP32-WROOM-32 və ya hər hansı ESP32 modulu |
| NeuroSky TGAM Modulu | 1 | ThinkGear ASIC Module - EEG siqnal prosessoru |
| EEG Sensor Dəsti | 1 | TGAM-a uyğun (qulaqcıq və alın sensorları) |
| Servo Motor (SG90/MG996R) | 5 | Robot barmaqları üçün |
| 5V 2A enerji mənbəyi | 1 | Servo motorları üçün |
| 3.3V LDO regulator (AMS1117) | 1 | TGAM modulu üçün (əgər TGAM 3.3V tələb edirsə) |
| Kondensator 470µF | 1 | Enerji təchizatı filtrasiyası |
| Jumper kabellər | - | Bağlantılar üçün |

## Bağlantı Sxemi

### TGAM -> ESP32

```
TGAM Modulu          ESP32
---------           -----
VCC (pin 1)   -->   3.3V
GND (pin 2)   -->   GND
TXD (pin 3)   -->   GPIO16 (UART2 RX)
```

**Qeyd:** TGAM modulu 3.3V və ya 5V ilə işləyə bilər. Modulun datasheet-inə əsasən düzgün gərginliyi təmin edin. Bəzi TGAM modulları 3.3V, bəziləri 5V tələb edir.

### Servo Motorlar -> ESP32

```
Servo        ESP32 Pin
-----        ---------
Thumb  -->   GPIO18
Index  -->   GPIO19
Middle -->   GPIO21
Ring   -->   GPIO22
Pinky  -->   GPIO23

Servo GND --> GND (ümumi)
Servo VCC --> 5V xarici enerji mənbəyi
```

**Vacib:** Servo motorları ESP32-nin daxili 3.3V regulatorundan enerji ALMAMALIDIR. Ayrı 5V enerji mənbəyi istifadə edin və GND-ləri birləşdirin.

## Enerji Təchizatı

```
[Xarici 5V] --+-- [470µF] --+-- Servo VCC (hamısı)
              |             |
             GND           GND

[ESP32 USB] -- 5V / 3.3V (ayrı)
```

## Fiziki Quraşdırma

1. TGAM modulunu EEG sensor dəstinə birləşdirin (qulaqcıq sol tərəf, alın sensoru)
2. TGAM TX pinini ESP32 GPIO16-ya birləşdirin
3. Servo motorları robot əl strukturuna yerləşdirin
4. Servo PWM siqnallarını ESP32-yə birləşdirin
5. Enerji təchizatını qurun
6. ESP32-ni USB ilə kompüterə qoşun

## TGAM Modulu Haqqında

NeuroSky TGAM (ThinkGear ASIC Module) aşağıdakı xüsusiyyətlərə malikdir:

- 57600 baud UART çıxışı
- Diqqət (attention) 0-100
- Meditasiya (meditation) 0-100
- Göz qırpma gücü (blink strength) 0-255
- Raw EEG dalğa forması
- 8 EEG tezlik bandı (delta, theta, alpha, beta, gamma)

TGAM modulunu almaq üçün:
- Aliexpress: "TGAM module" və ya "NeuroSky TGAM" axtarın
- Amazon: B01M0F8Q5B (MindWave klonu)
- Rəsmi: NeuroSky developer saytı
