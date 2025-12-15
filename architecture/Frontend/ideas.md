Sidebar 
  - 
    - Checkboxen für Hirach. und Spyker
    - Superserver: Name, Id, #-CPU, #-GPU
    - Server nodes: Name, Umgebung (Spyker oder Hierach.), #-CPU, #-GPU, Rechenzeit 
    - Client nodes: Id, #-Clients, Laptop/Workingstation/Mobile, Rechenzeit, Ping, Packetloss
    - Edges Button für Verbindungen 

Logik:
  - 
    - Clients untereinander nicht verbindbar
    - Verbindung Server untereinander nur mit Attribut Umgebung = Spyker
    - Verbindung Server mit Superserver nur mit Attribut Umgebung = Hierachical
    - Spyker angehakt, dadurch Superserver ausgegraut
    - Wenn Server ausgewählt wird, setze Attribut Umgebung auf Spyker 


Neue Todos:
  -
    - Start simulation: Popup Abfrage was man simulieren möchte 
      (Spyker, Hierachical oder beides)
    - Redo-, Undo- und Reset-Botton
    - Custome node noch weiter bearbeiten (Achtung bei type=default)
    - Umgebungsbox löschen, da wir zwei Tabs
    - Überlegung wegen Edges ob wir nciht generell im Modus bleiben um einfach Edges 
      zu zeichnen und Nodes zu verbinden
    - Nodes und Edges speichern wenn man aktualisiert 
    - Compare bearbeiten:
      1. Verschiedene Tabs für Spyker und Hierachical als Toggel statt zwei Button
      2. Vlt wenn Haken gesetzt springt er in den andern Tab 
      3. Wenn man Switched werden alle clients übernommen
