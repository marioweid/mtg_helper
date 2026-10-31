# MTG Helper

Begriffe für Commander-bezogene Vorschläge und ihren Quellenstand.

## Neue Karten

**Neue Karte**:
Eine erstmals innerhalb der letzten 60 UTC-Tage erschienene, Commander-legale Papierkarte, die die
bestehenden Quellenfilter und die Farbidentität der Commander-Konstellation erfüllt. Spoiler und
Neuauflagen alter Karten sind keine neuen Karten in diesem Sinn.
_Avoid_: Spoiler, Neuauflage

**Tag-Treffer**:
Eine neue Karte, deren direkt zugewiesenes Scryfall-Tag mit einem direkten Commander-Tag oder einem
dessen Nachfahren in Scryfalls Tag-Hierarchie übereinstimmt. Der Treffer beschreibt die Quelle und
keine Synergie, Regelinteraktion oder Eignung für die Deckstrategie.
_Avoid_: KI-Einschätzung, geprüfte Empfehlung, starker Fit

**Commander-Konstellation**:
Der alleinige Commander oder die gemeinsam gespeicherten Commander eines Decks, einschließlich
eines zweiten Commanders oder Backgrounds. Sie bestimmt, für welche Commander ein Vorschlag gilt,
nicht welche Strategie das Deck tatsächlich verfolgt. Die Konstellation ist keine Bestätigung einer
regelkonformen Commander-Paarung.
_Avoid_: Deckstrategie, Deckinhalt

**Decklokales Ausblenden**:
Das Entfernen bereits enthaltener, als Addition geplanter oder in diesem Deck verworfener Karten aus
dessen Trefferanzeige. Die Tag-Treffer anderer Decks bleiben gleich.
_Avoid_: Globale Ablehnung

**Quellenstatus**:
Der aktuelle, übereinstimmende Scryfall-Karten- und Tag-Stand. Fehlende, veraltete oder
unterschiedliche Generationen sind kein Ergebnis ohne Treffer.
_Avoid_: Keine passenden Karten

## Entdecken

**Discover-Strategie**:
Die vom Nutzer beschriebene oder aus einem KI-Vorschlag ausgewählte Ausrichtung eines Decks für
die Kartensuche. Ihr Text und die dazu ausgewählten Suchkriterien gehören zusammen, ohne dass
die Suchkriterien jede Aussage des Strategietexts ausdrücken müssen. Ein Vorschlag wird erst durch
bewusstes Speichern zur aktiven Discover-Strategie.
_Avoid_: Erkannte Deckstrategie, automatische Deckdiagnose

**Strategie-Suchkriterium**:
Ein für die Discover-Strategie ausgewähltes Oracle-Tag oder Gedrucktes Keyword aus Scryfall.
Suchkriterien können innerhalb einer Strategie-Suche als Alternativen oder gemeinsam notwendige
Merkmale kombiniert werden. Sie sind keine Bestätigung einer passenden Regelinteraktion.
_Avoid_: Erfundenes Kartenlabel, globale Strategiezuteilung

**Strategie-Suche**:
Eine ausgewählte Kombination von Suchkriterien und gegebenenfalls Kartentypen für ergänzende
Karten. Mehrere Strategie-Suchen sind alternative Zugänge; eine Karte muss nicht alle Suchen
erfüllen. Ein Kartentyp bezieht sich auf die Vorderseite, nicht auf eine erst später verfügbare
Rückseite oder eine angenommene Regelinteraktion.
_Avoid_: Geprüfte Rolle, Synergiebeweis, verpflichtende Deckquote

**Strategie-Treffer**:
Eine für die Commander-Konstellation zulässige Karte, die mindestens eine gewählte Strategie-
Suche erfüllt. Ein Oracle-Tag kann dabei über seine Nachfahren treffen. Der Treffer erklärt
die Quellenübereinstimmung, nicht eine bewiesene Synergie oder eine KI-Einzelbewertung der Karte.
Anders als ein Tag-Treffer in Neue Karten ist er nicht auf neue Veröffentlichungen beschränkt.
_Avoid_: Geprüfte Empfehlung, bewiesener Fit, KI-bewertete Karte

**Globale Beliebtheit**:
Die allgemeine Verbreitung einer Karte in Commander-Decks laut Kartenquelle, unabhängig von der
gewählten Commander-Konstellation oder Strategie. Ein fehlender Wert ist unbekannt, nicht schlecht.
_Avoid_: Commander-Synergie, Strategie-Eignung, Qualitätsnote

**Discover-Ausblendung**:
Die rückgängig machbare Entscheidung des Nutzers, einen Strategie-Treffer in einem bestimmten
Deck nicht anzuzeigen. Sie verändert weder die Discover-Strategie noch die Bewertung der Karte
für andere Decks.
_Avoid_: Globale Ablehnung, gelöschte Karte

## Kartenlabels

**Oracle-Tag**:
Ein von Scryfall bereitgestelltes globales Kartenlabel mit eigener Identität und Zuordnungen zu
Oracle-Karten. Übergeordnete Tags können untergeordnete Tags einschließen, ohne die direkte
Zuordnung einer Karte zu verändern.
_Avoid_: Regeltag, MTGJSON-Tag, Hub-Tag

**Gedrucktes Keyword**:
Eine von Scryfall als Kartenfakt bereitgestellte benannte Fähigkeit oder Mechanik.
Es ist kein aus Regeltext oder einer fremden Keyword-Liste nachträglich abgeleitetes Label.
_Avoid_: Erkanntes MTGJSON-Keyword

**Persönliche Kategorie**:
Eine vom Nutzer für sein Deck gewählte Einordnung, unabhängig von globalen Oracle-Tags.
Sie ist Nutzerabsicht, keine Tatsachenbehauptung über die globale Kartenklassifikation.
_Avoid_: Globales Kartenlabel
