# Hierarchical federated learning (HFL) across heterogeneous cellular networks

- Hierarchisch (nicht nur server-clients sondern mainserver - subserver - clients)
- federated stochastic gradient descent on decentralized datasets, werden random auf Clients verteilt und alle paar Intevalle, gibt es ein Pull, wo das auf subservern gemerged wird -> und später dann nochmal Pulls wo es dann auf den mainserver kommt
- techniken wie sparsification, periodic averaging, resource allocation strategy to minizime E2E latency
- Clients kriegen Dataset und Anzahl an lokalen updates --> nach dieser Anzahl geben sie dem Server ihr Update --> Server berechnet average von allen Clients, wiederholt sich solange, bis daten konvergieren (Entweder alle Clients oder nur Subset)
- diese kleineren Server schicken dann ihr update alle paar intervalle an den mainserver --> subserver kriegen auch unterschiedliche "Aufgaben"
- (deutlich) Bessere Latenz und auch bessere genauigkeit!

# Towards federated learning at scale: system design

- Runde: 1. Auswahl von Geräten (Teilnahmebedinungen) kleine Teilmenge (paar hundert), 2. FL Plan geht an ausgewähle Geräte, 3. Gerät trainiert und gibt Update an Server --> Server averaged die Ergebnisse (Geräte die nicht rechtzeitig fertig werden, werden ignoniert) - Server gibt Rückmeldezeitraum vor -> Serverüberlastung entgegenwirken
- UX nicht ficken, Multi-tenancy -> mehrere Modelle können gleichzeitig trainieren --> Nutzt Android-Funktion um kompromittierte Geräte auszusortieren
- Skalierbar für Millionen von Geräten! Actor programming Model -> Kommunikation über nachrichten, Coordinator - Selector (Sucht Geräte) - Master Aggregator (Für jede Runde erneut erstellt, leitet die Runde)- Aggregator (Sammelt Updates von Geräten)
- flüchtige Zustände - nur im RAM gespeichert für Dauer der Runde --> besserer speed & privatsphäre (keine permanenten Logs)
- Pipelining (selection-phase startet, während reporting noch läuft)
- Fehlertoleranz, da sich alles wieder gegenseitig spawnen kann
- Anonymität, Gerätdaten mitschicken (Dauer Training & Ablauf, Auslastung etc., aber auch Daten zur Fehleranalyse)
- Secure Aggregation (siehe learning differentially private recurrent language models)
- TensorFlow verwendet
- Real World example: Gboard und Settingssuche
- Probleme: Bias, Bandbreite effizienter Nutzen (Compression)

# Learning differentially private recurrent language models

- stochastic gradient descent
- tastatur am handy wenn man sensitive data eingibt (z.B. pw)
- deren methode, hat nicht wirklich die genauigkeit etc. verändert

# Sonstiges

- Data Poisoning
