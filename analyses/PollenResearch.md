# Bachelorforschungspojekt - Research - Pollen #
Nico Reng
## Generelle Sachen ##
1. Neuartiges ressourcenbewusstes System zur Beschleunigung von Simulationen. Ineffiziente Kommunikation aufgrund der Pull-basierten Client-Ausführung und unzureichender Lastverteilung bei Verwendung heterogener Hardware.
2. Führt FL-Simulationen mit hohem Durchsatz in großem Maßstab durch, indem es ein Push-basiertes Client-Platzierungssystem verwendet und dabei lernt, wie eine anpassungsfähige Planung von Clients auf der Grundlage von Hardware-Statistiken, die die optimale Anzahl gleichzeitiger Worker pro GPU schätzen, durchgeführt werden kann.
3. Bewertung anhand von vier FL-Aufgaben und Nachweis, dass Pollen die GPU-Auslastung erhöht und die Leerlaufzeit reduziert.
4. Vergleich von Pollen mit Flower, Flute, FedScale, Parrot und pfl und Nachweis einer experimentellen Beschleunigung um Tage oder Wochen.
5. **Architektur**: 
Verwendet ein Push-basiertes Client-Platzierungssystem und ein parallelitätsbewusstes Machine-Learning-Modell, um die optimale Anzahl gleichzeitiger Worker pro GPU zu schätzen, die Ressourcennutzung zu maximieren und die Leerlaufzeit zu reduzieren. 
6. **Kommunikation/Topologie**: 
Minimiert die Kommunikation zwischen Maschinen. Verwendet Ring-AllReduce für die teilweise Aggregation auf Knotenebene (innerhalb der Maschine) und einen Standard-Parameter-Server-Ansatz, um die Knotenergebnisse asynchron (zwischen den Knoten) zu kombinieren. Es ist für eine hohe Konnektivität innerhalb der Maschine optimiert, erfordert jedoch keine extrem schnelle Kommunikation zwischen den Knoten.
7. **Wesentlicher Vorteil für Multi-Server/Heterogenität**:
Das lernbasierte (LB) Platzierungsmodell verteilt Clients intelligent auf heterogene GPUs in einer einmaligen Zuweisung, prognostiziert die Trainingszeit, berücksichtigt unterschiedliche Hardware-Geschwindigkeiten und schätzt automatisch die optimale Anzahl gleichzeitiger Worker (Concurrency Estimator).
8. FL sind aktuell nicht für große Simulationen $10^6$ Devices nicht optimiert. Pollen beseitigt die Einschränkung indem es die Ausführungszeit großer Simulationen gängiger ML-Aufgaben von Monaten auf Wochen reduziert, wenn es auf Clustern mit mehreren Knoten mit unausgewogenen GPUs ausgeführt wird siehe Abschnitt 5.2 und Abschnitt 6.
9. Zwei Probleme 1. Clients mit großen Datasets sind limitiert in den Contributions. 2. Kleinere müssen data reusen.
10. Werden auch Vielfältigkeit der verwendeten Hardware berücksichtigt und wie das client Training beeinflusst. Client workloads sind kleiner als normale ML tasks und höher parallelisierbar. Jede FL-Aufgabe wird als eine Verteilung isolierter einzelner ML-Aufgaben von clients definiert die iterativ geplant und in jeder Runde aggregiert werden. Also sodass $10^3 - 10^4$ clients per round  feasible sein können müssen researchers und practitioners diverse GPUs across verios servers leveragen. 
11. Die meisten Frameworks (Flute, FedScale, Flower) usen eine communicatin-heavy pull based queuing system, wo der Server FL-Simulationen koordiniert, indem er Clients an Worker-Prozesse auf GPUs weiterleitet.
Pull-based hat 2 Nachteile: 
Workers können nicht auswählen, welchen Clients sie trainieren möchten, dadurch ist Lastverteilung eingeschränkt, welche erforderlich sind um die Auswirkungen natürlich partitionierter Datensätze zu mildern. Das gleichzeitige Abrufen eines einzelnen clients kann auch zu einem Kommunikationsaufwand führen, insbesondere wenn die Datensätze der clients klein sind und die Trainingszeiten mit dem Abrufen von Aufträgenvergleichbar sind.
12. Jedes Framework hat limitations: 
Flute: used nur ein single worker per GPU
FedScale: Lädt das ganze Dataset auf jeden worker, handling large datasets schwierig
Flower: Hängt von Ray als Simulations-Engine, die geplante Jobs auf der Festplatte serialisiert, wodurch sich die Latenz erhöht. 
13. Apple hat ein framework für Private Federated Learning veröffentlicht was interessant wäre. Es behandelt alle workers als ein member einer flachen topology. Es used Ring

## Pollen Design ##
### Hauptfunktion ###

1. Wollen folgendes erreichen: 
Maximieren vom experimental throughput and Effizient beim Ressourcenverbrauch (der es ermöglicht, die verfügbaren Ressourcen zu nutzen, unabhängig davon, ob diese heterogen, beträchtlich oder begrenzt sind). Flexibility also um jede user-definierte ML task auf jeder Hardware runnen zu lassen, ohne den Pollen source code zu ändern. Leztes ist user-friendly as possible. Um das zu schaffen maximiert Pollen die Vorteile von Push-Based Communicaiton, durch Berücksichtigung der Last- und Hardwarevielfalt durch das Push-basierte Platzierungssystem.

2. **Minimale Server-GPU-Kommunikation:** Erreicht durch Push-basiertes System und die Unterstützung von partieller Aggregation. Dies reduziert die Datenübertragung und erleichtert die Skalierung über mehrere Knoten hinweg.

3. **Effektive GPU-Parallelität:** Ermöglicht durch eine automatische Schätzung der Parallelität auf jeder GPU.

4. **Load-balancing method:** Verwendet ein robustes, parallelitätsbewusstes Machine-Learning-Modell zur Schätzung der Client-Trainingszeit auf einer GPU, was die Leerlaufzeiten der GPU minimiert.


### Kernbereich ####

**Push-Basierte Platzierung:** 

Pollen führt eine Push-basierte Zuweisung von Client-Arbeitslasten auf GPUs durch, anstatt dass Worker Clients vom Server anfordern, indem er die Client-Workloads auf die GPUs aufteilt.
* One-Shot-Zuweisung: Der Server sendet nur eine Kopie des globalen Modells an jeden Knoten, gefolgt von einer Liste der Client-IDs, die der jeweiligen GPU auf diesem Knoten zugewiesen sind. (Weil halt jede GPU in einem Knoten gehostet wird)
* Dies reduziert die Anzahl der Kommunikationsschritte zwischen Server und Knoten und ermöglicht die Zuweisung von Client-Sets zu geeigneten GPUs.
* Die Platzierung erfolgt auf der Simulationsebene und ist unabhängig vom eigentlichen FL-Algorithmus (z. B. Client-Auswahlmethode).

**Concurrency Estimator (CE):**

Pollen definiert einen neuartigen Schätzer, um das optimale Parallelitätsniveau/-grad zu bestimmen, das eine GPU für eine gegebene Aufgabe unterstützen kann, ohne manuelle Abstimmung. Die Datenaquise passiert auf node leve, also keine Synchronisation notwendig. Der CE bekommt infos über verfügbare Hardware. Also Anzahl der CPU cores, sowie Nummern und Typen der GPUs und Grad der Parallelität den sie erreichen können.

* Ziel: Die gleichzeitige Ausführung mehrerer Worker-Prozesse auf derselben GPU ist vorteilhaft für kleine Trainingslasten, aber zu viele Prozesse führen zu Thrashing und verlängern die Trainingszeit.

* Ablauf: Die maximale Parallelität wird geschätzt, indem zunächst ein Client trainiert und Statistiken wie VRAM-Allokation und GPU-Auslastung gesammelt werden.

* Anschließend wird die Anzahl der Worker schrittweise erhöht, bis sich die Ausführungsgeschwindigkeit auf dieser GPU nicht mehr verbessert oder die maximale Anzahl an Workern erreicht ist.

* Der Prozess läuft unabhängig und gleichzeitig für jede GPU ab, um die Effizienz zu optimieren. Dadurch muss der Benutzer die Anzahl der Prozesse nicht manuell konfigurieren.

**High-Scaleable Partial Aggregation:**

Bei assoziativen Aggregationsstrategien (wie FedAvg) reduziert Pollen die Kommunikationskosten und -dauer, indem Client-Ergebnisse innerhalb der Worker und Knoten partiell aggregiert werden, bevor die Teilergebnisse zur vollständigen Aggregation an den Server gesendet werden.

* Mechanismus: Nach Abschluss des Trainings durch alle Worker berechnet der Knoten eine partielle Aktualisierung ($\theta^w$), die an den Server gesendet wird, indem die Worker-Modelle mithilfe von Ring AllReduce aggregiert werden. 

    * *Info zu Ring AllReduce: Wenn jede GPU nur einen worker hostet und intra-machine GPUs connected sind, ist die bandwidth optimal weil sie linear skaliert in der Anzahl der Parameter und ist nur von der kleinsten bandwidth connection zwischen GPUs abhängig*

* Lokalität: Pollen führt Ring AllReduce nur innerhalb einer einzigen Maschine aus. Dies ermöglicht es, die hohe Bandbreite von Intra-Maschinen-GPUs optimal zu nutzen, ohne die strengen Bandbreitenanforderungen von Inter-Maschinen-Systemen erfüllen zu müssen.
Wegen Kommunikation pro Runde statt pro Batch, werden keine großen Anforderungen an die Bandbreite gestellt, da die Verwendung von vielen aber schlecht verbundenen GPUs die Effizienz trotzdem steigert. Pollen benutzt Ring AllReduce innerhalb einer Maschine, um so die größtmögliche Bandbreite zu erlangen.

* Nicht-Assoziative Algorithmen: Kommunikation weiterhin nur einmal vom Server zu Workers. Für FL-Algorithmen, die nicht assoziativ sind (z. B. Robust Aggregation), wird ein Paket aller Client-Modelle von den Workern an die Knoten und dann an den Server gesendet.

### Client Placement Model ###
Während Pollen die Kommunikationseffizienz früherer Arbeiten durch seine Push-basierte Client-Platzierung verbessert, verhindert die zur Optimierung der Kommunikation verwendete
Einmalzuweisung eine Laufzeit-Client-Neuzuweisung zwischen Knoten.
Um Clients über GPUs hinweg auszugleichen und Nachzügler zu vermeiden, muss der Server daher die Trainingszeit jedes Clients auf einer GPU vorhersagen. 

### Platzierungsstruktur und Baseline ###

Das Platzierungsmodell muss eine Liste von $N$ zufällig ausgewählten Clients in einem Schritt auf die Worker der verschiedenen GPUs verteilen. Es ist Parallelitäts-bewusst und weist Clients pro Worker und nicht pro gesamter GPU zu. Um die Trainingszeit vorherzusagen, stützt es sich auf die Anzahl der Batches eines Clients.

* **Naive Round-Robin (RR) Platzierung (Baseline):** Verteilt Clients gleichmäßig auf die Worker. Dies ist robust für homogene Clients und Hardware , führt aber bei heterogener Hardware oder Last zu Ungleichgewicht und Leerlaufzeiten.

* **Batches-Based (BB) Platzierung (Baseline):** Versucht, die Arbeit zu verteilen, indem es die Anzahl der Batches der Clients über die Worker hinweg ausgleicht. Dieses Verfahren ignoriert jedoch die Unterschiede in der GPU-Geschwindigkeit und die komplexe Skalierung der Trainingszeit mit der Batch-Anzahl.

### Lernbasiertes (LB) Platzierungsmodell ###
Da die Batch-Anzahl allein aufgrund der inneren und äußeren Variablen (z. B. Betriebssystem-Scheduling, Systemlast) eine unzureichende Schätzung der Trainingszeit ist, verwendet Pollen ein lernbasiertes Modell.

* Fitting-Funktion: Das Modell passt eine *log-lineare Kurve* an die Trainingszeitdaten an: $$f(x) = ax + b \log(cx) + d$$ Diese Funktion wurde gewählt, weil sie empirische Verteilungen besser abbildet als eine einfache lineare Funktion (niedrigeres SSE). Sie verhindert insbesondere, dass das Modell negative Trainingszeiten vorhersagt, was bei kleinen Clients mit hoher Varianz geschehen kann.

* Initialisierung: Die ersten beiden Runden verwenden die Naïve RR-Platzierung, um unvoreingenommene Daten zur Trainingszeit von allen Workern zu sammeln. Ab der dritten Runde wird das log-lineare Modell verwendet.

* Platzierungslogik: Das LB-Verfahren sortiert die Worker nach GPU-Typ (schnellste zuerst). Es weist dann die Clients (geordnet nach der größten Batch-Anzahl zuerst) dem Worker mit der geringsten Gesamtlast zu.

### Robuste und Adaptive Modellierung ###
* Robustheit: Pollen speichert alle Daten aus früheren Runden für die Anpassung der Kurve, um die Robustheit der Vorhersage zu erhöhen.

* Adaptive Fehlerkorrektur: Um Abweichungen vom erwarteten Trend und zeitabhängige Systemeffekte (z. B. Lastverschiebungen) zu berücksichtigen, verwendet Pollen eine adaptive Fehlerkorrektur.

## Experimental Design ##
### FL Tasks ###

Es wurden vier repräsentative FL-Aufgaben verwendet, die jeweils eine eigene Modellarchitektur und ein natürlich föderiertes Dataset umfassen. Bei allen Experimenten wurde Federated Averaging mit einer lokalen Epoche verwendet.

* Image Classification (IC): ShuffleNetV2 auf einer föderierten Version des Open Image Datasets. 
* Speech Recognition (SR): ResNet-34 auf dem Google Speech Commands Dataset (natürlich auf 2168 Sprecher partitioniert). 
* Text Generation (TG): Zwei-Zellen-LSTM auf dem Shakespeare Dataset (nach 648 fiktiven Charakteren gruppiert). 
* Masked Language Modelling (MLM): RoBERTa auf dem Reddit Dataset (enthält $1.6 \times 10^6$ Clients).

### Hardware-Konfigurationen ###

* **Single Node:**
Homogen, Nvidia A40 (Node 0), eine einzige GPU in einemhomogenen Setup, um den Einfluss der Push-basiertenKommunikation zu testen

* **Multi-Node:**
Heterogen, Nvidia A40 (Node 0) + 3x Nvidia 2080 Ti (Node 1), eine Kombination aus zwei verschiedenen GPU-Typen, wobei die VRAM-Kapazitäten über beide GPU-Typen hinweg ausgeglichen sind.

* **Skalierbarkeit der Kohortengröße** 
Die Skalierung wurde gemessen, indem die Größe der föderierten Population und die Anzahl der Clients pro Runde erhöht wurden. Dabei wurden stets 0,1 % der simulierten Population ausgewählt, um reale Anwendungen zu spiegeln. 


* **Modellevaluierung**
Es wurde der Einfluss des Platzierungsmodells (LB Placement) auf die GPU-Auslastung und die Leerlaufzeit bewertet. Pollen wurde hierzu mit der Round-Robin (RR) Baseline verglichen.

## Evaluierung ##
**Homogene Single-Node-Vergleiche**
* Pollen verbessert die Simulationszeit selbst auf eingeschränkter, homogener Hardware (Single-Node, Nvidia A40). 

* Die Push-basierte Kommunikation und die effektive Parallelitätsnutzung ermöglichen es Pollen, schnellere Simulationszeiten zu erzielen als die nächstbesten Frameworks (Flower/Parrot), da es die geringe Größe der Client-Jobs optimal ausnutzt. 

* Implikation: Pollen maximiert den Durchsatz und die Flexibilität bei begrenzten Ressourcen.

**Diverse Hardware Multi-Node-Vergleiche** 
* In heterogenen Multi-Node-Umgebungen werden die Geschwindigkeitssteigerungen durch Pollen noch größer. 
* Die Ergebnisse belegen die entscheidende Bedeutung der Client-Platzierung: Die Fähigkeit von Pollen, Client-Lasten über verschiedene GPUs hinweg auszubalancieren, ermöglicht es, den Vorsprung gegenüber pull-basierten Frameworks (wie Flower) auszubauen. 

**Skalierbarkeitsvergleiche** 
* Die Vorteile von Pollen kumulieren sich mit steigendem Maßstab, was beispiellos schnelle Simulationen für große und sehr große FL-Einstellungen ermöglicht. 

* Zeitersparnis: Pollen spart Monate an Trainingszeit für sehr große Experimente im Vergleich zu allen Konkurrenten. Beispielsweise dauert die Speech Recognition Aufgabe auf der größten Skala mit Pollen nur zwei Wochen, während der schnellste Konkurrent zwei Monate benötigt. 

* Implikation: Pollen ist der einzige FL-Simulator, der Forschung in den für reale Anwendungen notwendigen Maßstäben ermöglicht. 

## Effizienz des Platzierungsmodells ## 
* Das Learning-Based (LB) Placement Model von Pollen lernt, welche GPU-Geräte schneller trainieren, und weist ihnen eine größere Arbeitslast zu, um die Simulationsgeschwindigkeit zu erhöhen. 

* Messung: Im Multi-Node-Szenario minimierte Pollen die GPU-Leerlaufzeit über alle Aufgaben hinweg im Vergleich zu den Baselines RR und Batches-Based (BB) deutlich. 

* Implikation: Pollen kann GPUs zu einer höheren Auslastung antreiben, wenn dies die Geschwindigkeit des Experiments verbessert. 

## Beitrag der Partiellen Aggregation ## 
Die Partielle Aggregation trägt zwar zur Effizienz bei, aber die Platzierungsmodell, der Parallelitätsschätzer und das Push-basierte Design machen den Großteil der Geschwindigkeitssteigerung von Pollen aus. Die Zeitersparnis durch Pollen war immer eine Größenordnung größer als die Zeit, die für die vollständige Aggregation benötigt wurde.