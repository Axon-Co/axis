# TGAM ThinkGear Protokolu

## Ümumi Məlumat

TGAM modulu 57600 baud, 8 bit, 1 stop bit, parity yoxdur parametrləri ilə UART üzərindən məlumat göndərir.

## Paket Strukturu

```
[Sync1] [Sync2] [Length] [Payload...] [Checksum]
  1 byte  1 byte  1 byte   N byte       1 byte
```

- **Sync1/Sync2:** 0xAA 0xAA - paket başlanğıcı
- **Length:** Payload uzunluğu (1-255)
- **Payload:** Məlumat sətirləri (aşağıya bax)
- **Checksum:** Payload byte-larının cəminin bitwise NOT-u

## Payload Sətir Strukturu

Hər payload sətiri bir kod və dəyərdən ibarətdir.

### Sadə sətir (code < 0x80):
```
[Code] [Value]
  1b     1b
```

### Mürəkkəb sətir (code >= 0x80):
```
[Code] [Length] [Value(s)]
  1b     1b       N b
```

## Kod Cədvəli

| Kod | Adı | Uzunluq | Dəyər | İzah |
|-----|-----|---------|-------|------|
| 0x02 | Poor Signal | 1 | 0-255 | 0 = yaxşı, >200 = zəif siqnal |
| 0x04 | Attention | 1 | 0-100 | Diqqət səviyyəsi |
| 0x05 | Meditation | 1 | 0-100 | Meditasiya səviyyəsi |
| 0x16 | Blink Strength | 1 | 1-255 | Göz qırpma gücü |
| 0x80 | Raw Wave | 2 | -32768..32767 | Xam EEG dalğası |
| 0x83 | EEG Power | 24 | 8 x 3 byte | Tezlik zolaqları |

## EEG Power Formatı (0x83)

3 byte big-endian unsigned integer, 8 band:

| Offset | Band |
|--------|------|
| 0-2 | Delta |
| 3-5 | Theta |
| 6-8 | Low Alpha |
| 9-11 | High Alpha |
| 12-14 | Low Beta |
| 15-17 | High Beta |
| 18-20 | Low Gamma |
| 21-23 | High Gamma |

## Misal Paket

```
AA AA 04 04 50 05 60 AB

AA AA        - Sync
04           - Length = 4
04 50        - Attention = 80
05 60        - Meditation = 96
AB           - Checksum (~(0x04+0x50+0x05+0x60))
```

## Axis Komanda Strukturu

### Rejimlər

| Dəyər | Rejim | İzah |
|-------|-------|------|
| 0 | MODE_GRIP | Attention -> barmaq qüvvəsi |
| 1 | MODE_FINGER_SELECT | Beyin dalğaları ilə barmaq seçimi |
| 2 | MODE_SEQUENCE | Hərəkət ardıcıllığını qeyd/oynat |
| 3 | MODE_CALIBRATE | Kalibrasiya rejimi |

### MODE_GRIP

- Attention 0-30: Açıq əl
- Attention 30-70: Xətti nəzarət
- Attention 70-100: Tam qapalı əl
- Göz qırpma: Sürətli aç/qapa

### MODE_FINGER_SELECT

- Yüksək attention + aşağı meditation: Baş barmaq
- Yüksək attention + yüksək meditation: İndeks
- Aşağı attention + yüksək meditation: Orta
- Orta attention: Üzük
- Göz qırpma: Növbəti barmağa keç
