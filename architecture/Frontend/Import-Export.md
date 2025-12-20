- User gibt eine JSON als Import ein (Graph Import) oder erstellt selbst einen neuen Graphen

- Sende diesen an das Backend 

- Unterschied zwischen zwei Werten: (Speicherung voraussichtlich mit Hashwert oder evtl. eine ID)
    1. Node list
    2. Edge list

- Zwischen Datenbank und Frontend und Engines von Max und Vio

- Später kann der User dann die Graphen aus der Datenbank nehmen und verwenden. 

Folgender Ablauf: 
-
    1. Import eines Graphen (JSON Format)/ Neuerstellung eines Graphen 
    2. Graph wird abgesendet an das Backend von Deniz im JSON Format
    3. Serializing von Objekten und speichern diese in der Datenbank (bzw. Daten und Edges)
    4. Berechne die Hashwerte um zu prüfen ob sich ein Graph verändert hat oder nicht
    5. Sende den Graph immer und sofort nach Update. (z.B. Neue Node eingefügt, sende direkt die         Aktualisierung ans Backend)
    6. Berechnung von Max und Vio
   #### - Genauere Ausarbeitung der nachstehenden Punkte folgen noch:
    7. Rückendung der Metriken und Ergebnisse an Backend von Deniz 
    8. Weiterleitung der Ergebnisse an Frontend 
    9. Deserializing der Daten und Darstellung

