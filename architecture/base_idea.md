# *Base idea* 

**Max**
-
- Flat Multiserver
- SPYKER basiert
- Erstellung einer Schnittstelle zum Simulationsstart
- weiteres in Zukunft nach Planung/Architektur
<br>
<br>


**Vio**
-
- Hierachie Server
- Extend Python Classes
- Schnittstelle für Konfigurator
- weiteres in Zukunft nach Planung/Architektur
<br>
<br>

**Deniz**
-
- Backend um die Simulation zu starten
- Wechsel danach in Serverstrukturen 
- Hardware Profiles for Clients (Ping simulation) $\rightarrow$ auf dieser Grundlage haben wir dann Geo-Routing
<br>
<br>
<u> Überlegungen </u>
- Parser
- JSON Graphstruktur
- Endpunkte für Nutzerinteraktion
<br>
<br>
<u> Max Unterstützung </u>
- Zuordnung von Ressourcen/Rechenleistung für Simulation
- Aufbau Simulationsnetzwerk (Ray Simulation Framework)
- Genaueres später weil Architketur noch nicht genau geplant 
<br>
<br>

**Silas / Nico**
-
<u> Generell:  </u>
- Konfiguration und Mertriken (Frontend)
- Logs schreiben
- Vergleiche ansetzen 
- Graph-/ Netzwerkstruktur
- Prozesstracking
- Schnittstelle zu User
- Generelle Zahlen für Metriken (Performance (auch auf Clients), Response time, Effizienz, Trainingloss, Accuracy, Restarts, Fairness, Skalierbarkeit etc.) diese sind bezogen auf Federal Learning $\rightarrow$ *Absprache mit Michael*
- Simulation aufsetzen $\rightarrow$ mit Deniz
- Überlegung zur Vorkonfiguartion 
- Template (Beispiel 3 Server mit avg. Ping verbunden und dann je ein paar Clients an den jedweiligen Servern anhängen)
- Daten aufbereiten aus Datalake (preperation)
<br>
<br>
<u> Oberfläche:  </u>
- Minimalistisch halten
- Voraussichtlich zwei Arten von Knoten (Client und Server)
- Dropdownmenü
- Graph (Synch / Asynch) 
- Client configuration: Mobile Client, Connection Type (WIFI, LAN, etc), Packetloss, Anzahl der Clients 
- (**Vermeiden: Server initialisieren und dann Clients einzelnd verbinden**  )
- Metriken als CSV Download
- Knopf für CIFAR-10 Start 
<br>
<br>
<u> Nächste Schritte: </u>

- HFL/Spyker Select-Button
- Customs Nodes (Server/Client) mit den richtigen properties definieren
  - Client: Mobile Unit/Workstation/Laptop, Anzahl
- Edges (Client/Server, Server/Sever, Nicht Client/Client)
  - Edges properties: Latency/Packetloss
- Client/Server im Dropdownmenü (einfügen)
- Nodes löschen
- Vorwärts/Zurückbutton

<br>
<br>

Weitere Überlegungen
- 
- Wenn mit CIFAR-10 funktioniert und Flower-AI es einfach ermöglicht, kann man Plug-In-Play Datensatz vom Nutzer ausgehend vorschreiben lassen (Datensatz muss heruntergeladen sein und wegen Splitting auf Client)
<br> 
Könnte man vielleicht machen indem sich die Clients aus einem Ordner den abgelegten Datensatz ziehen. (Nicht Push-basiert)
- Michael bzgl. Repo fragen $\rightarrow$ wurde eingerichtet und auch Projekt
<br>
<br>
<br>
## Links
- #### NGX: https://www.ngx-vflow.org/getting-started/what-is-ngx-vflow
- #### D3Js: https://d3js.org
- #### Huggingface: https://huggingface.co/datasets
- #### Flower-AI-Dataset: https://flower.ai/docs/datasets
