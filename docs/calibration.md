# EspBrain - Kalibrasiya Bələdçisi

## 1. EEG Sensorunun Qurulması

### TGAM Düzgün Qoşulma

1. Qulaqcıq sol qulağa taxılır (clip hissə)
2. Alın sensoru düz alnın ortasına yerləşdirilir
3. Sensor saçla təmasda OLMAMALIDIR
4. Dəri təmiz və quru olmalıdır

### Siqnal Keyfiyyəti Göstəriciləri

- **poor_signal = 0:** Mükəmməl siqnal
- **poor_signal 1-50:** Qənaətbəxş
- **poor_signal 50-200:** Zəif - sensoru düzəldin
- **poor_signal > 200:** Siqnal yoxdur

## 2. Kalibrasiya Rejimi

ESP32-də MODE_CALIBRATE rejiminə keçin. Bu rejimdə EEG məlumatları USB serial port üzərindən çap olunur:

```
[Calibrate] Signal=0 Att=45 Med=62 Blink=0
[Calibrate] Signal=0 Att=72 Med=38 Blink=0
[Calibrate] Signal=0 Att=68 Med=45 Blink=200
```

### Monitorinq:

```bash
idf.py monitor
# və ya screen /dev/ttyUSB0 115200
```

## 3. Attention Kalibrasiyası

1. Rahat bir vəziyyətdə oturun
2. Bir obyektə fokuslanın (məsələn, ekrandakı nöqtə)
3. Attention dəyərini qeyd edin (normal: 40-80)
4. 30 saniyə gözləyin (istirahət)
5. Attention dəyərini yenə qeyd edin

**threshold_low** = ortalama istirahət attention + 5
**threshold_high** = ortalama fokus attention - 5

## 4. Meditation Kalibrasiyası

1. Gözlərinizi yumun
2. Dərin nəfəs alın
3. Meditation dəyərini qeyd edin
4. Normal istirahət halınızı tapın

## 5. Göz Qırpma Kalibrasiyası

1. Normal göz qırpma edin (hər 3-5 saniyədən bir)
2. blink_strength dəyərlərini qeyd edin
3. Normal qırpmalar 50-150 arasıdır
4. **blink_threshold** = ortalama dəyər + 30

## 6. Servo Kalibrasiyası

Hər bir servo üçün min və max açıları təyin edin:

1. Servo_controller.h-də `servo_configs` massivini redaktə edin
2. `min_angle` - barmağın tam açıq olduğu bucaq
3. `max_angle` - barmağın tam qapalı olduğu bucaq
4. `home_position` - başlanğıc (istirahət) mövqeyi
5. `invert` - servo əks istiqamətdə dönürsə true

## 7. Sürət Tənzimləməsi

`smoothin_factor` dəyəri hərəkət sürətini idarə edir:
- **10-30:** Yavaş, hamar hərəkətlər
- **40-60:** Orta sürət (tövsiyə olunan)
- **70-100:** Sürətli hərəkətlər

## 8. Tez-tez Problemlər

| Problem | Səbəb | Həll |
|---------|-------|------|
| poor_signal > 0 | Sensor düzgün qoyulmayıb | Sensoru düzəldin, dərini təmizləyin |
| Attention həmişə 0 | TGAM bağlantısı yoxdur | UART pinlərini yoxlayın |
| Servo titrəyir | Enerji çatışmazlığı | Ayrı 5V enerji mənbəyi istifadə edin |
| Servo hərəkət etmir | PWM konfiqurasiyası | LEDC parametrlərini yoxlayın |
| Blink aşkarlanmır | Threshold çox yüksək | threshold dəyərini azaldın |
